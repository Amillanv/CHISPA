"""The growth risk at two moments: which alerts become a large fire.

The confidence asks if an alert matches a mapped fire of the minimum area. The growth risk
asks the same question at higher limits of hectares, with the same inputs and the same model.
It asks only for a new fire: the alert that saw a mapped fire first. A later alert on that
fire is on a known fire. `docs/method.md` section 11.21 gives the rules.
"""

import json
import sqlite3
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
from chispa.evaluation.report import config_hash, share

KEPT = ("inputs", "size_ha", "advance_m", "alert", "matched")  # What the file of a year keeps.
TENTHS = 10  # The groups of the calibration table. A fifth is too wide for a rare outcome.


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
    """Return the rows that the growth risk can score, each with the size of its alert.

    The size of an alert is the area of the largest fire that it saw first: a new fire.
    An alert that saw no fire first has the size 0: no mapped fire. An alert is left out if
    its detections at the moment match a fire that a different alert saw first: a known fire.
    """
    largest: dict[int, float] = {}
    for fire, alert in first.items():
        largest[alert] = max(largest.get(alert, 0.0), float(area_ha[fire]))
    return [
        {**row, "size_ha": largest.get(row["alert"], 0.0)}
        for row in rows
        if all(first[fire] == row["alert"] for fire in row["own_fires"])
    ]


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


def measures(values: np.ndarray, size: np.ndarray, limit_ha: float) -> dict:
    """Return how well one value finds the alerts that became large: a fire of the limit or more.

    `auc_new_fires` uses only the alerts with a new fire: there a value must put the sizes
    in a sequence, not only find the alerts with a fire.
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
        "new_fires": int(new_fire.sum()),
        "auc_new_fires": separation(values[new_fire], large[new_fire]),
        "largest_fires": int((size >= config.RISK_LARGEST_HA).sum()),
        "top_tenth_largest_fires": int((size[top] >= config.RISK_LARGEST_HA).sum()),
    }


def result_table(kept: dict[str, list], models: dict, confidence_models: dict) -> list[dict]:
    """Return the measures of the growth risk and of each baseline, for each moment and limit."""
    table = []
    for moment in MOMENTS:
        rows, baseline = kept[moment], confidence_models[moment]
        size = np.array([row["size_ha"] for row in rows])
        compared = {
            "confidence": confidence.probability(baseline, _inputs(rows, baseline)),
            "detections": np.array([row["inputs"]["detections_log"] for row in rows]),
        }
        if moment == MOMENTS[-1]:
            # An alert with no measured advance gets the lowest place: the persistence rule
            # says that a fire with no growth in the last pass does not grow.
            compared["persistence"] = np.array([row["advance_m"] or 0.0 for row in rows])
        for limit in config.RISK_LIMITS_HA:
            model = models[key(moment, limit)]
            risk = {"growth_risk": confidence.probability(model, _inputs(rows, model))}
            for name, values in (risk | compared).items():
                row = {"moment_h": moment, "limit_ha": limit, "value": name}
                table.append(row | measures(values, size, limit))
    return table


def _inputs(rows: list[dict], model: dict) -> np.ndarray:
    return as_table(rows, tuple(model["inputs"]))[0]


def calibration_table(kept: dict[str, list], models: dict) -> list[dict]:
    """Return, for each model, the values of the growth risk against what came.

    The first row of a model is for all alerts, with the Brier score and its skill against one
    constant: the base rate of the training years. Then one row for each tenth of the alerts,
    in the sequence of the value. `above_lower_limit` counts the alerts with a larger value
    than for the lower limit: their two values give no probability for the class between.
    """
    table = []
    for moment in MOMENTS:
        rows, lower = kept[moment], None
        size = np.array([row["size_ha"] for row in rows])
        for limit in config.RISK_LIMITS_HA:
            model = models[key(moment, limit)]
            chance, large = confidence.probability(model, _inputs(rows, model)), size >= limit
            brier = float(((chance - large) ** 2).mean())
            constant = float(((model["base_rate"] - large) ** 2).mean())
            first = _calibration_row(chance, large) | {
                "brier": round(brier, 5),
                "brier_skill": round(1 - brier / constant, 4),
                "above_lower_limit": None if lower is None else int((chance > lower).sum()),
            }
            parts = np.array_split(np.argsort(chance, kind="stable"), TENTHS)
            groups = [("all", first)] + [
                (str(number), _calibration_row(chance[part], large[part]))
                for number, part in enumerate(parts, 1)
            ]
            table += [
                {"moment_h": moment, "limit_ha": limit, "group": name} | row for name, row in groups
            ]
            lower = chance
    return table


def _calibration_row(chance: np.ndarray, large: np.ndarray) -> dict:
    return {
        "alerts": len(large),
        "probability_mean": round(float(chance.mean()), 4),
        "large": int(large.sum()),
        "large_share": share(large.sum(), len(large)),
        "expected_large": round(float(chance.sum()), 1),
        "observed_to_expected": share(large.sum(), chance.sum()),
    }


def group_table(rows: dict[str, list], kept: dict[str, list], fires: Fields) -> list[dict]:
    """Return, for each moment, the alerts of each group, and the new fires by fire size class.

    `fires` is the number of counted fires of the class in the year. A fire is not a new fire
    of its class if the alert that saw it first is left out, or also saw a larger fire first.
    """
    table = []
    limits = (*config.EVAL_SIZE_CLASSES_HA, np.inf)
    for moment in MOMENTS:
        size = np.array([row["size_ha"] for row in kept[moment]])
        groups = [
            ("all alerts", len(rows[moment]), None),
            ("known fire: left out", len(rows[moment]) - len(size), None),
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


def saved_rows(year: int, store_path: Path, raw_dir: Path) -> dict:
    """Return the rows of one year that the growth risk can score, and its table of groups.

    The rows of a year are slow to make, and each run needs the rows of each year. A file in
    the data folder keeps them, with a mark of the configuration and of the fusion of the year.
    """
    first_id = year * 10_000_000
    count = "SELECT COUNT(*) FROM memberships WHERE event_id >= ? AND event_id < ?"
    span = (first_id, first_id + 10_000_000)
    mark = f"{config_hash()}-{sqlite3.connect(store_path).execute(count, span).fetchone()[0]}"
    path = store_path.parent / "risk" / f"{year}.json"
    if path.exists() and (found := json.loads(path.read_text()))["mark"] == mark:
        return found
    rows, (detections, pairs, fires) = year_rows(year, store_path, raw_dir)
    first = seen_first(detections, pairs, fires)
    kept = {moment: sized_rows(rows[moment], first, fires["area_ha"]) for moment in MOMENTS}
    found = {
        "mark": mark,
        "kept": {m: [{name: row[name] for name in KEPT} for row in kept[m]] for m in MOMENTS},
        "alerts": group_table(rows, kept, fires),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(found))
    return found


def risk_tables(year: int, store_path: Path, raw_dir: Path) -> dict[str, list[dict]]:
    """Return the tables of the growth risk for one year, from models that did not see that year.

    The models get their weights from each other year with mapped fires: a cross-validation
    by year. The baseline of the confidence is its saved model, with no change.
    """
    if year not in config.YEAR_ROLES:
        raise RuntimeError(f"{year} has no mapped fires in the store. The growth risk needs them.")
    saved = {other: saved_rows(other, store_path, raw_dir) for other in config.YEAR_ROLES}
    training = {
        moment: [row for other in saved if other != year for row in saved[other]["kept"][moment]]
        for moment in MOMENTS
    }
    models = fit_models(training)
    path = config.RESULTS_DIR / str(config.DEVELOPMENT_YEAR) / "confidence" / "model.json"
    return {
        "risk": result_table(saved[year]["kept"], models, confidence.load(path)),
        "risk_calibration": calibration_table(saved[year]["kept"], models),
        "risk_alerts": saved[year]["alerts"],
        "risk_weights": weight_table(models),
    }
