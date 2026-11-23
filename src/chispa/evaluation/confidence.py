"""The confidence at two moments, against the mapped fires and against the level rule.

For each event we make the inputs at the first alert and 24 hours later. The development year
gives the weights of the model. Each other year uses that model with no change.
The question: does the probability separate the events that match a mapped fire
better than the level that the fusion gave at the same moment?
"""

from pathlib import Path

import numpy as np
from scipy import stats

from chispa import confidence, config, severity
from chispa.evaluation.match import Fields, Pairs
from chispa.evaluation.report import share
from chispa.evaluation.run import prepare
from chispa.evaluation.severity import newest_advance
from chispa.fusion import LEVELS

MOMENTS = ("0", "24")
FIFTHS = 5


def moment_rows(detections: Fields, matched: set[int], layers: severity.Layers) -> dict[str, list]:
    """Return, for each moment, one row for each event: its inputs, its level and its label."""
    order = np.argsort(detections["event"], kind="stable")
    starts = np.nonzero(np.concatenate([[True], np.diff(detections["event"][order]) != 0]))[0]
    limits = {"0": config.PASS_GAP.total_seconds(), "24": config.SEVERITY_EVAL_HOURS * 3600}
    rows = {moment: [] for moment in MOMENTS}
    for start, end in zip(starts, [*starts[1:], len(order)], strict=True):
        members = order[start:end]
        available = detections["available"][members]
        event = int(detections["event"][members[0]])
        for moment, limit_s in limits.items():
            chosen = members[available <= available.min() + limit_s]
            row = _event_row(detections, chosen, layers)
            row["matched"] = event in matched
            rows[moment].append(row)
    return rows


def _event_row(detections: Fields, chosen: np.ndarray, layers: severity.Layers) -> dict:
    lat, lon = detections["lat"][chosen], detections["lon"][chosen]
    advance_m = newest_advance(detections, chosen)
    found = severity.facts(lat, lon, detections["frp_mw"][chosen], advance_m, layers)
    first = chosen[detections["observed"][chosen].argmin()]
    seen = {
        "families": set(detections["family"][chosen].tolist()),
        "has_high": bool(detections["high"][chosen].any()),
        "day": int(detections["day"][first]),
        "local_hour": (detections["observed"][first] / 3600 + detections["lon"][first] / 15) % 24,
    }
    newest = chosen[detections["available"][chosen] == detections["available"][chosen].max()]
    level = max(LEVELS.index(name) for name in detections["level"][newest])
    return {"inputs": confidence.inputs(found, seen), "level": level}


def names_of(moment: str) -> tuple[str, ...]:
    """Return the input names of one moment."""
    return confidence.INPUTS + (confidence.LATER_INPUTS if moment == "24" else ())


def as_table(rows: list[dict], names: tuple[str, ...]) -> tuple[np.ndarray, np.ndarray]:
    """Return the inputs of the events as an array, and the labels as an array."""
    table = np.array([[row["inputs"][name] for name in names] for row in rows])
    return table, np.array([row["matched"] for row in rows], dtype=float)


def separation(values: np.ndarray, matched: np.ndarray) -> float | None:
    """Return the probability that an event with a match has a larger value than one with none."""
    is_match = matched > 0
    ranks = stats.rankdata(values)
    higher = ranks[is_match].sum() - is_match.sum() * (is_match.sum() + 1) / 2
    return share(higher, is_match.sum() * (~is_match).sum())


def result_tables(rows: dict[str, list], models: dict[str, dict]) -> dict[str, list[dict]]:
    """Return the table of the separation and the table of the calibration."""
    compare, calibration = [], []
    for moment in MOMENTS:
        table, matched = as_table(rows[moment], tuple(models[moment]["inputs"]))
        chance = confidence.probability(models[moment], table)
        level = np.array([row["level"] for row in rows[moment]], dtype=float)
        for name, values in (("probability", chance), ("level", level)):
            compare.append(
                {
                    "moment_h": moment,
                    "measure": name,
                    "events": len(matched),
                    "events_matched": int(matched.sum()),
                    "match_separation": separation(values, matched),
                }
            )
        for number, part in enumerate(np.array_split(np.argsort(chance, kind="stable"), FIFTHS), 1):
            calibration.append(
                {
                    "moment_h": moment,
                    "fifth": number,
                    "events": len(part),
                    "probability_mean": round(float(chance[part].mean()), 4),
                    "matched_share": share(matched[part].sum(), len(part)),
                }
            )
    return {"confidence": compare, "confidence_calibration": calibration}


def weight_table(models: dict[str, dict]) -> list[dict]:
    """Return the weight of each input at each moment, the largest first."""
    table = []
    for moment in MOMENTS:
        pairs = zip(models[moment]["inputs"], models[moment]["weights"], strict=True)
        for name, weight in sorted(pairs, key=lambda pair: -abs(pair[1])):
            table.append({"moment_h": moment, "input": name, "weight": round(weight, 4)})
    return table


def matched_events(detections: Fields, pairs: Pairs, fires: Fields) -> set[int]:
    """Return each event with a detection that matches a counted fire."""
    counted = fires["counted"][pairs[1]]
    return set(np.unique(detections["event"][pairs[0][counted]]).tolist())


def confidence_tables(year: int, store_path: Path, raw_dir: Path) -> dict[str, list[dict]]:
    """Return the tables of the confidence for one fused year.

    The development year makes the model and saves it. Each other year reads that model.
    """
    detections, pairs, fires, _ = prepare(year, store_path, raw_dir)
    layers = severity.load_layers(raw_dir, year - 1)
    rows = moment_rows(detections, matched_events(detections, pairs, fires), layers)
    path = config.RESULTS_DIR / str(config.DEVELOPMENT_YEAR) / "confidence" / "model.json"
    if year == config.DEVELOPMENT_YEAR:
        models = {}
        for moment in MOMENTS:
            names = names_of(moment)
            models[moment] = confidence.fit(*as_table(rows[moment], names), names)
        confidence.save(models, path)
    models = confidence.load(path)
    tables = result_tables(rows, models)
    if year == config.DEVELOPMENT_YEAR:
        tables["confidence_weights"] = weight_table(models)
    return tables
