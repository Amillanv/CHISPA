"""The growth risk at two moments: which alerts become a large fire.

The confidence asks if an alert matches a mapped fire of the minimum area. The growth risk
asks the same question at higher limits of hectares, with the same inputs and the same model.
It asks only for a new fire: the alert that saw a mapped fire first. A later alert on that
fire is on a known fire. `docs/method.md` section 11.21 gives the rules.
"""

from pathlib import Path

import numpy as np

from chispa import confidence, config
from chispa.evaluation.confidence import (
    MOMENTS,
    as_table,
    names_of,
    separation,
    top_tenth,
    year_rows,
)
from chispa.evaluation.match import Fields, Pairs
from chispa.evaluation.report import share
from chispa.evaluation.risk_calibration import calibration_table

Tables = dict[str, list[dict]]


def seen_first(detections: Fields, pairs: Pairs, fires: Fields) -> dict[int, int]:
    """Return, for each counted fire, the alert that saw it first.

    That alert had the match with the earliest `available` time. If two alerts have a match
    at that time, it is the alert with the smaller id.
    """
    counted = fires["counted"][pairs[1]]
    position, fire = pairs[0][counted], pairs[1][counted]
    order = np.lexsort((detections["issued"][position], detections["available"][position], fire))
    numbers, starts = np.unique(fire[order], return_index=True)
    alerts = detections["issued"][position[order][starts]]
    return dict(zip(numbers.tolist(), alerts.astype(int).tolist(), strict=True))


def sized_rows(rows: list[dict], first: dict[int, int], area_ha: np.ndarray) -> list[dict]:
    """Return each row with the size of its alert, and a mark for an alert on a known fire.

    `size_ha` is the area of the largest fire that the alert saw first: a new fire. With no
    such fire it is 0: no mapped fire. `seen_ha` uses only the fires that the detections of the
    alert match at the moment. `known` says that those detections match a fire that a different
    alert saw first: the models do not learn from that alert, and the main tables leave it out.
    """
    largest: dict[int, float] = {}
    for fire, alert in first.items():
        largest[alert] = max(largest.get(alert, 0.0), float(area_ha[fire]))
    sized = []
    for row in rows:
        own = [fire for fire in row["own_fires"] if first[fire] == row["alert"]]
        sizes = {
            "size_ha": largest.get(row["alert"], 0.0),
            "seen_ha": max((float(area_ha[fire]) for fire in own), default=0.0),
            "known": len(own) < len(row["own_fires"]),
        }
        sized.append(row | sizes)
    return sized


def new_or_none(rows: list[dict]) -> list[dict]:
    """Return the rows of the alerts that are not on a known fire."""
    return [row for row in rows if not row["known"]]


def key(moment: str, limit_ha: float) -> str:
    """Return the name of the model of one moment and one limit."""
    return f"{moment}h_{limit_ha:g}ha"


def fit_models(kept: dict[str, list]) -> dict[str, dict]:
    """Return one model for each moment and each limit, from the rows of the training years."""
    models = {}
    for moment in MOMENTS:
        names = names_of(moment)
        table, _ = as_table(kept[moment], names)
        size = np.array([row["size_ha"] for row in kept[moment]])
        for limit in config.RISK_LIMITS_HA:
            models[key(moment, limit)] = confidence.fit(table, (size >= limit) * 1.0, names)
    return models


def average_precision(values: np.ndarray, large: np.ndarray) -> float | None:
    """Return the area below the curve of precision against recall.

    Alerts with equal values are one step of the curve. A random sequence gives the base rate.
    """
    if not large.any():
        return None
    order = np.argsort(-values, kind="stable")
    in_order, hits = values[order], large[order]
    last = np.append(in_order[1:] != in_order[:-1], True)  # The last alert of each equal value.
    found = np.cumsum(hits)[last]
    precision = found / (np.flatnonzero(last) + 1)
    gained = np.diff(np.concatenate([[0], found]))
    return round(float((precision * gained).sum() / hits.sum()), 4)


def measures(values: np.ndarray, size: np.ndarray, seen: np.ndarray, limit_ha: float) -> dict:
    """Return how well one value finds the alerts that became large: a fire of the limit or more.

    `auc_new_fire_alerts` uses only the alerts with a new fire: there a value must put the sizes
    in a sequence, not only find the alerts with a fire. `auc_at_moment` has a label from the
    fires that an alert matches at the moment, and not from a fire that its event reached later.
    """
    large, new_fire, top = size >= limit_ha, size > 0, top_tenth(values)
    return {
        "alerts": len(size),
        "large": int(large.sum()),
        "base_rate": share(large.sum(), len(size)),
        "auc": separation(values, large),
        "average_precision": average_precision(values, large),
        "top_tenth": len(top),
        "top_tenth_large": int(large[top].sum()),
        "precision_top_tenth": share(large[top].sum(), len(top)),
        "recall_top_tenth": share(large[top].sum(), large.sum()),
        "new_fire_alerts": int(new_fire.sum()),
        "auc_new_fire_alerts": separation(values[new_fire], large[new_fire]),
        "large_at_moment": int((seen >= limit_ha).sum()),
        "auc_at_moment": separation(values, seen >= limit_ha),
        "largest_alerts": int((size >= config.RISK_LARGEST_HA).sum()),
        "top_tenth_largest_alerts": int((size[top] >= config.RISK_LARGEST_HA).sum()),
    }


def values_of(rows: list[dict], model: dict, baseline: dict, with_advance: bool) -> dict:
    """Return each value that the tables compare, for the rows of one moment and one limit."""
    values = {
        "growth_risk": confidence.probability(model, as_table(rows, tuple(model["inputs"]))[0]),
        "confidence": confidence.probability(
            baseline, as_table(rows, tuple(baseline["inputs"]))[0]
        ),
        "detections": np.array([row["inputs"]["detections_log"] for row in rows]),
    }
    if with_advance:
        # An alert with no measured advance gets the lowest place: the persistence rule
        # says that a fire with no growth in the last pass does not grow.
        values["persistence"] = np.array([row["advance_m"] or 0.0 for row in rows])
    return values


def result_table(kept: dict[str, list], models: dict, confidence_models: dict) -> list[dict]:
    """Return the measures of the growth risk and of each baseline, for each moment and limit."""
    table = []
    for moment in MOMENTS:
        rows, last = kept[moment], moment == MOMENTS[-1]
        size = np.array([row["size_ha"] for row in rows])
        seen = np.array([row["seen_ha"] for row in rows])
        for limit in config.RISK_LIMITS_HA:
            compared = values_of(rows, models[key(moment, limit)], confidence_models[moment], last)
            for name, values in compared.items():
                row = {"moment_h": moment, "limit_ha": limit, "value": name}
                table.append(row | measures(values, size, seen, limit))
    return table


def all_alerts_table(sized: dict[str, list], area_ha: np.ndarray, models: dict, others: dict):
    """Return what the top tenth of all alerts reaches, with no group left out.

    A brigade gets each alert: only the map of the year says which alerts are on a known fire.
    A fire is reached if the detections of an alert of the top tenth match it at the moment.
    `large` is the number of large alerts of the main table, and `top_tenth_large` is how many
    of them are in this top tenth. `others` has the models of the confidence.
    """
    table = []
    for moment in MOMENTS:
        rows, last = sized[moment], moment == MOMENTS[-1]
        known = np.array([row["known"] for row in rows])
        size = np.array([0.0 if row["known"] else row["size_ha"] for row in rows])
        for limit in config.RISK_LIMITS_HA:
            reached = [{f for f in row["own_fires"] if area_ha[f] >= limit} for row in rows]
            compared = values_of(rows, models[key(moment, limit)], others[moment], last)
            for name, values in compared.items():
                top = top_tenth(values)
                counts = {
                    "alerts": len(rows),
                    "known_fire_alerts": int(known.sum()),
                    "top_tenth": len(top),
                    "top_tenth_known_fire_alerts": int(known[top].sum()),
                    "large_fires": len(set().union(*reached)),
                    "top_tenth_large_fires": len(set().union(*(reached[i] for i in top))),
                    "large": int((size >= limit).sum()),
                    "top_tenth_large": int((size[top] >= limit).sum()),
                }
                table.append({"moment_h": moment, "limit_ha": limit, "value": name} | counts)
    return table


def group_table(sized: dict[str, list], fires: Fields) -> list[dict]:
    """Return, for each moment, the alerts of each group, and the new fires by fire size class.

    `fires` is the number of counted fires of the class in the year. A fire is not a new fire
    of its class if the alert that saw it first is left out, or also saw a larger fire first.
    """
    table = []
    limits = (*config.EVAL_SIZE_CLASSES_HA, np.inf)
    for moment in MOMENTS:
        size = np.array([row["size_ha"] for row in new_or_none(sized[moment])])
        groups = [
            ("all alerts", len(sized[moment]), None),
            ("known fire: left out", len(sized[moment]) - len(size), None),
            ("no mapped fire", int((size == 0).sum()), None),
        ]
        for low, high in zip(limits[:-1], limits[1:], strict=True):
            in_class = (fires["area_ha"] >= low) & (fires["area_ha"] < high)
            alerts = int(((size >= low) & (size < high)).sum())
            groups.append((f"new fire, {low:g} to {high:g} hectares", alerts, int(in_class.sum())))
        table += [
            {"moment_h": moment, "group": group, "alerts": alerts, "fires": number}
            for group, alerts, number in groups
        ]
    return table


def weight_table(models: dict[str, dict]) -> list[dict]:
    """Return the weight of each input of each model, the largest first."""
    table = []
    for name, model in models.items():
        pairs = zip(model["inputs"], model["weights"], strict=True)
        for input_name, weight in sorted(pairs, key=lambda pair: -abs(pair[1])):
            table.append({"model": name, "input": input_name, "weight": round(weight, 4)})
    return table


def year_parts(year: int, store_path: Path, raw_dir: Path) -> dict:
    """Return the rows of one year with their sizes, the areas of its fires and its groups."""
    rows, (detections, pairs, fires) = year_rows(year, store_path, raw_dir)
    first = seen_first(detections, pairs, fires)
    sized = {moment: sized_rows(rows[moment], first, fires["area_ha"]) for moment in MOMENTS}
    return {"rows": sized, "area_ha": fires["area_ha"], "alerts": group_table(sized, fires)}


def risk_tables(store_path: Path, raw_dir: Path) -> dict[int, Tables]:
    """Return the tables of the growth risk for each year with mapped fires.

    The numbers of a year come from models that each other year trained: a cross-validation by
    year. One run makes the rows of each year and each table: no file keeps a part of it, thus
    all tables have the same code, the same store and the same configuration.
    """
    parts = {year: year_parts(year, store_path, raw_dir) for year in config.YEAR_ROLES}
    path = config.RESULTS_DIR / str(config.DEVELOPMENT_YEAR) / "confidence" / "model.json"
    baselines, tables = confidence.load(path), {}
    for year, part in parts.items():
        models = fit_models(_training(parts, [other for other in parts if other != year]))
        kept = {moment: new_or_none(part["rows"][moment]) for moment in MOMENTS}
        tables[year] = {
            "risk": result_table(kept, models, baselines),
            "risk_all_alerts": all_alerts_table(part["rows"], part["area_ha"], models, baselines),
            "risk_calibration": calibration_table(kept, models),
            "risk_alerts": part["alerts"],
            "risk_weights": weight_table(models),
        }
        # The split in time sequence: the weights come only from the years before the year.
        if earlier := [other for other in parts if other < year]:
            models = fit_models(_training(parts, earlier))
            tables[year]["risk_earlier"] = result_table(kept, models, baselines)
            tables[year]["risk_calibration_earlier"] = calibration_table(kept, models)
    return tables


def _training(parts: dict[int, dict], years: list[int]) -> dict[str, list]:
    return {
        moment: [row for year in years for row in new_or_none(parts[year]["rows"][moment])]
        for moment in MOMENTS
    }
