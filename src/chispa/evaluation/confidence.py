"""The confidence at two moments, against the mapped fires and against the level rule.

For each event we make the inputs at the first alert and 24 hours later. The development year
gives the weights of the model. Each other year uses that model with no change.
The question: does the probability separate the events that match a mapped fire
better than the level that the fusion gave at the same moment?
"""

import sqlite3
from pathlib import Path

import numpy as np
from scipy import stats

from chispa import confidence, config, severity
from chispa.evaluation.match import Fields, Pairs
from chispa.evaluation.moments import at_moments, load_merges
from chispa.evaluation.report import share
from chispa.evaluation.run import prepare
from chispa.evaluation.severity import newest_advance
from chispa.fusion import LEVELS

MOMENTS = ("0", "24")
FIFTHS = 5
TOP_SHARE = 0.1  # The part of the events with the largest values that a brigade can go to first.
DAY_S = 86_400


def activity(detections: Fields) -> tuple[np.ndarray, tuple]:
    """Return the number of detections in each day and each cell, and how to find a cell.

    The count is by the day when a detection became available. Thus the count of the days
    before a day uses only data that existed on that day.
    """
    west, south, east, north = config.PANTANAL_BOX
    side = config.CONFIDENCE_NEAR_CELL_DEG
    days = (detections["available"] // DAY_S).astype(int)
    rows = ((detections["lat"] - south) / side).astype(int) + 1  # One free cell at each edge.
    cols = ((detections["lon"] - west) / side).astype(int) + 1
    shape = (
        days.max() - days.min() + 1,
        int((north - south) / side) + 3,
        int((east - west) / side) + 3,
    )
    counts = np.zeros(shape, dtype=np.int32)
    np.add.at(counts, (days - days.min(), rows, cols), 1)
    return counts, (int(days.min()), south, west, side)


def near_count(counts: np.ndarray, place: tuple, time_s: float, lat: float, lon: float) -> int:
    """Return the detections of the days before a time, in the cell of a position and around it."""
    first_day, south, west, side = place
    day = int(time_s // DAY_S) - first_day
    row, col = int((lat - south) / side) + 1, int((lon - west) / side) + 1
    before = counts[
        max(day - config.CONFIDENCE_NEAR_DAYS, 0) : day, row - 1 : row + 2, col - 1 : col + 2
    ]
    return int(before.sum())


def moment_rows(detections: Fields, merges: list, links: tuple, layers: severity.Layers):
    """Return, for each moment, one row for each alert: its inputs, its level and its label.

    An alert is the event as it was at the moment (`moments.py`). `links` has the counted fires
    that each event of the end of the year matches, and the counted fires of each detection.
    An alert has a match if the event that holds it at the end of the year has one.
    `own_fires` has only the fires that the detections of the alert at the moment match.
    """
    fires_of, (first_link, link_fire) = links
    limits = {"0": config.PASS_GAP.total_seconds(), "24": config.SEVERITY_EVAL_HOURS * 3600}
    counts, place = activity(detections)
    rows = {moment: [] for moment in MOMENTS}
    for moment, alert, own, chosen in at_moments(detections, merges, limits):
        first = own[detections["available"][own].argmin()]
        position = (detections["lat"][first], detections["lon"][first])
        near = near_count(counts, place, detections["available"][first], *position)
        row = _alert_row(detections, chosen, layers, near)
        row["alert"], row["positions"] = alert, chosen
        row["at"] = float(detections["available"][first]) + limits[moment]
        row["fires"] = fires_of.get(int(detections["event"][first]), frozenset())
        spans = [link_fire[first_link[d] : first_link[d + 1]] for d in chosen.tolist()]
        row["own_fires"] = frozenset(np.concatenate(spans).tolist())
        row["matched"] = bool(row["fires"])
        row["event"] = int(detections["event"][first])
        rows[moment].append(row)
    return rows


def _alert_row(detections: Fields, chosen: np.ndarray, layers: severity.Layers, near: int) -> dict:
    lat, lon = detections["lat"][chosen], detections["lon"][chosen]
    advance_m = newest_advance(detections, chosen)
    found = severity.facts(lat, lon, detections["frp_mw"][chosen], advance_m, layers)
    first = chosen[detections["observed"][chosen].argmin()]
    seen = {
        "families": set(detections["family"][chosen].tolist()),
        "has_high": bool(detections["high"][chosen].any()),
        "day": int(detections["day"][first]),
        "local_hour": (detections["observed"][first] / 3600 + detections["lon"][first] / 15) % 24,
        "near": near,
    }
    newest = chosen[detections["available"][chosen] == detections["available"][chosen].max()]
    level = max(LEVELS.index(name) for name in detections["level"][newest])
    return {"inputs": confidence.inputs(found, seen), "level": level, "advance_m": advance_m}


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


def top_tenth(values: np.ndarray) -> np.ndarray:
    """Return the positions of the tenth of the events with the largest values."""
    return np.argsort(-values, kind="stable")[: int(len(values) * TOP_SHARE)]


def scores(name: str, values: np.ndarray, chance: np.ndarray, matched: np.ndarray, base: float):
    """Return the row of one measure. `chance` is its probability for each event.

    The Brier value is the mean square of the probability minus the label: 0 is the best.
    The Brier skill compares it with one constant probability, the matched share of the
    development year: more than 0 is better than that constant.
    """
    top = top_tenth(values)
    brier = float(((chance - matched) ** 2).mean())
    constant = float(((base - matched) ** 2).mean())
    return {
        "measure": name,
        "alerts": len(matched),
        "alerts_matched": int(matched.sum()),
        "match_separation": separation(values, matched),
        "brier": round(brier, 4),
        "brier_skill": round(1 - brier / constant, 4),
        "top_tenth": len(top),
        "top_tenth_matched": int(matched[top].sum()),
    }


def result_tables(rows: dict[str, list], models: dict[str, dict]) -> dict[str, list[dict]]:
    """Return the table of the comparison with the level, and the table of the calibration.

    The probability of a level is the matched share of that level in the development year.
    The calibration puts the events in sequence by their probability and makes equal groups.
    For each group: the mean probability that the model gave, and the matched share that came.
    """
    compare, calibration = [], []
    for moment in MOMENTS:
        model = models[moment]
        table, matched = as_table(rows[moment], tuple(model["inputs"]))
        chance = confidence.probability(model, table)
        level = np.array([row["level"] for row in rows[moment]])
        level_chance = np.array(model["level_rates"])[level]
        for name, values, given in (
            ("probability", chance, chance),
            ("level", level, level_chance),
        ):
            row = scores(name, values.astype(float), given, matched, model["base_rate"])
            # Many events can match one large fire. Thus we also count the different fires.
            top = [rows[moment][position] for position in top_tenth(values.astype(float))]
            row["top_tenth_fires"] = len(frozenset().union(*(alert["fires"] for alert in top)))
            # The fires above come from the event of the end of the year: a later merge can
            # add them. These fires come only from the detections of the alert at the moment.
            row["top_tenth_own_fires"] = len(frozenset().union(*(a["own_fires"] for a in top)))
            compare.append({"moment_h": moment, **row})
        for number, part in enumerate(np.array_split(np.argsort(chance, kind="stable"), FIFTHS), 1):
            calibration.append(
                {
                    "moment_h": moment,
                    "fifth": number,
                    "alerts": len(part),
                    "probability_mean": round(float(chance[part].mean()), 4),
                    "matched_share": share(matched[part].sum(), len(part)),
                    # 1 is a correct probability. More than 1: the probability is too low.
                    "observed_to_predicted": share(matched[part].sum(), chance[part].sum()),
                }
            )
    return {"confidence": compare, "confidence_calibration": calibration}


def level_rates(rows: list[dict], base: float) -> list[float]:
    """Return the matched share of each level. A level with no event gets the share of all."""
    rates = []
    for level in range(len(LEVELS)):
        labels = [row["matched"] for row in rows if row["level"] == level]
        rates.append(float(np.mean(labels)) if labels else base)
    return rates


def weight_table(models: dict[str, dict]) -> list[dict]:
    """Return the weight of each input at each moment, the largest first."""
    table = []
    for moment in MOMENTS:
        pairs = zip(models[moment]["inputs"], models[moment]["weights"], strict=True)
        for name, weight in sorted(pairs, key=lambda pair: -abs(pair[1])):
            table.append({"moment_h": moment, "input": name, "weight": round(weight, 4)})
    return table


def event_fires(detections: Fields, pairs: Pairs, fires: Fields) -> dict[int, frozenset]:
    """Return the counted fires that each event matches."""
    counted = fires["counted"][pairs[1]]
    links = np.unique(np.stack([detections["event"][pairs[0][counted]], pairs[1][counted]]), axis=1)
    found: dict[int, set] = {}
    for event, fire in zip(*links.tolist(), strict=True):
        found.setdefault(event, set()).add(fire)
    return {event: frozenset(numbers) for event, numbers in found.items()}


def detection_fires(
    detections: Fields, pairs: Pairs, fires: Fields
) -> tuple[np.ndarray, np.ndarray]:
    """Return the counted fires of each detection, as two arrays.

    The fires of the detection at position d are `fire[first[d] : first[d + 1]]`.
    """
    counted = fires["counted"][pairs[1]]
    order = np.argsort(pairs[0][counted], kind="stable")
    positions, fire = pairs[0][counted][order], pairs[1][counted][order]
    first = np.searchsorted(positions, np.arange(len(detections["event"]) + 1))
    return first, fire


def year_rows(
    year: int, store_path: Path, raw_dir: Path, matched: tuple | None = None
) -> tuple[dict[str, list], tuple]:
    """Return the rows of each moment for one fused year, and its detections, matches and fires.

    `matched` has the detections, the matches and the fires of a year whose fires are not in
    the store: a year with no annual map.
    """
    detections, pairs, fires = matched or prepare(year, store_path, raw_dir)[:3]
    layers = severity.load_layers(raw_dir, severity.cover_year(year))
    merges = load_merges(sqlite3.connect(store_path), year)
    links = (event_fires(detections, pairs, fires), detection_fires(detections, pairs, fires))
    return moment_rows(detections, merges, links, layers), (detections, pairs, fires)


def confidence_tables(year: int, store_path: Path, raw_dir: Path) -> dict[str, list[dict]]:
    """Return the tables of the confidence for one fused year.

    The development year makes the model and saves it. Each other year reads that model.
    """
    rows, _ = year_rows(year, store_path, raw_dir)
    path = config.RESULTS_DIR / str(config.DEVELOPMENT_YEAR) / "confidence" / "model.json"
    if year == config.DEVELOPMENT_YEAR:
        models = {}
        for moment in MOMENTS:
            names = names_of(moment)
            models[moment] = confidence.fit(*as_table(rows[moment], names), names)
            models[moment]["level_rates"] = level_rates(rows[moment], models[moment]["base_rate"])
            # The values of the alerts of this year, in sequence. A value of a new alert gets
            # its rank from them: the share of these values that are smaller.
            values = confidence.probability(models[moment], as_table(rows[moment], names)[0])
            models[moment]["reference"] = np.sort(values).round(6).tolist()
        confidence.save(models, path)
    models = confidence.load(path)
    tables = result_tables(rows, models)
    if year == config.DEVELOPMENT_YEAR:
        tables["confidence_weights"] = weight_table(models)
    return tables
