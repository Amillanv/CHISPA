"""The severity against the outcome that we can measure: the mapped area of the fires of an event.

The severity is a heuristic. This module asks if it says more than a simple count:
does an event with a high severity, some hours after its first detection, end with more
burned ground than an event with a low severity?
"""

import sqlite3
from pathlib import Path

import numpy as np
from scipy import stats

from chispa import config, growth, severity
from chispa.evaluation.match import Fields, Pairs
from chispa.evaluation.moments import at_moments, load_merges
from chispa.evaluation.report import percentile, share
from chispa.evaluation.run import prepare

INPUTS = {"max_frp_mw": "fire power, MW", "extent_km": "extent, km", "advance_m": "advance, m"}
BASELINES = ("severity", "detections", "max_frp_mw", "extent_km")


def outcomes(detections: Fields, pairs: Pairs, fires: Fields) -> dict[int, float]:
    """Return the mapped area of the counted fires that each event matches, in hectares."""
    counted = fires["counted"][pairs[1]]
    links = np.unique(np.stack([detections["event"][pairs[0][counted]], pairs[1][counted]]), axis=1)
    events, position = np.unique(links[0], return_inverse=True)
    areas = np.bincount(position, weights=fires["area_ha"][links[1]])
    return dict(zip(events.tolist(), areas.tolist(), strict=True))


def newest_advance(detections: Fields, chosen: np.ndarray) -> float | None:
    """Return the advance of the newest VIIRS step of an event, or None for no measured advance."""
    viirs = chosen[detections["family"][chosen] == growth.SENSOR_FAMILY]
    if len(viirs) < 2:
        return None
    observed = detections["observed"][viirs].astype(float)
    numbers = growth.passes(detections["platform"][viirs], observed)
    steps = growth.steps(detections["lat"][viirs], detections["lon"][viirs], numbers, observed)
    return steps[-1]["advance_m"] if steps and steps[-1]["new_pixels"] else None


def alert_rows(
    detections: Fields, merges: list, areas: dict, layers: severity.Layers
) -> list[dict]:
    """Return the facts, the severity and the outcome of each alert, at the evaluation time.

    An alert is the event as it was at that time (`moments.py`). Its outcome is the outcome of
    the event that holds it at the end of the year. `days_after` is the time from the
    evaluation time to the last detection of that event.
    """
    limit_s = config.SEVERITY_EVAL_HOURS * 3600
    last_s: dict[int, float] = {}
    pairs = zip(detections["event"].tolist(), detections["observed"].tolist(), strict=True)
    for event, observed in pairs:
        last_s[event] = max(observed, last_s.get(event, observed))
    rows = []
    for _, _, own, chosen in at_moments(detections, merges, {"24": limit_s}):
        lat, lon = detections["lat"][chosen], detections["lon"][chosen]
        advance_m = newest_advance(detections, chosen)
        found = severity.facts(lat, lon, detections["frp_mw"][chosen], advance_m, layers)
        event = int(detections["event"][own[0]])
        found["severity"] = severity.score(found)[0]
        found["area_ha"] = areas.get(event, 0.0)
        start_s = float(detections["available"][own].min())
        found["days_after"] = (last_s[event] - start_s - limit_s) / 86_400
        rows.append(found)
    return rows


def inputs_table(rows: list[dict]) -> list[dict]:
    """Return the percentiles of each input that gets its steps from the development year.

    An event has a value if the value is larger than zero. An event with no fire power or no
    measured advance has None. An event at one position has an extent of zero: it has no extent.
    """
    table = []
    for name, label in INPUTS.items():
        values = [row[name] for row in rows if row[name] is not None and row[name] > 0]
        values = np.array(values, dtype=float)
        table.append(
            {
                "input": label,
                "alerts": len(rows),
                "alerts_with_a_value": len(values),
                "p50": percentile(values, 50),
                "p75": percentile(values, 75),
                "p90": percentile(values, 90),
            }
        )
    return table


def score_table(rows: list[dict]) -> list[dict]:
    """Return, for each class of the severity, how many events match a fire and how much burned.

    `detected_after` counts the matched events with a detection after the evaluation time.
    `days_after` is the time from the evaluation time to the last detection of those events.
    """
    scores = np.array([row["severity"] for row in rows])
    areas = np.array([row["area_ha"] for row in rows])
    days = np.array([row["days_after"] for row in rows])
    limits = config.SEVERITY_SCORE_CLASSES
    classes = [
        (f"{low:g} to {min(high, 100):g}", (scores >= low) & (scores < high))
        for low, high in zip(limits[:-1], limits[1:], strict=True)
    ]
    table = []
    for label, part in (*classes, ("all", np.ones(len(rows), dtype=bool))):
        matched = part & (areas > 0)
        table.append(
            {
                "severity": label,
                "alerts": int(part.sum()),
                "alerts_matched": int(matched.sum()),
                "matched_share": share(matched.sum(), part.sum()),
                "area_ha_median": percentile(areas[matched], 50),
                "area_ha_p90": percentile(areas[matched], 90),
                "detected_after": int((matched & (days > 0)).sum()),
                "days_after_median": percentile(days[matched & (days > 0)], 50),
                "days_after_p90": percentile(days[matched & (days > 0)], 90),
            }
        )
    return table


def rank_table(rows: list[dict]) -> list[dict]:
    """Return how well the severity and each simple measure agree with the outcome.

    A measure uses only the events where it has a value: `events` is their number.
    `match_separation` is the probability that an event with a match has a larger value than
    an event with no match. 0.5 is no separation.
    """
    table = []
    for name in BASELINES:
        known = [row for row in rows if row[name] is not None]
        values = np.array([row[name] for row in known], dtype=float)
        areas = np.array([row["area_ha"] for row in known])
        matched = areas > 0
        ranks = stats.rankdata(values)
        higher = ranks[matched].sum() - matched.sum() * (matched.sum() + 1) / 2
        among_matched = stats.spearmanr(values[matched], areas[matched]).statistic
        table.append(
            {
                "measure": name,
                "alerts": len(known),
                "rank_correlation": round(float(stats.spearmanr(values, areas).statistic), 4),
                "alerts_matched": int(matched.sum()),
                "match_separation": share(higher, matched.sum() * (~matched).sum()),
                "rank_correlation_matched": round(float(among_matched), 4),
            }
        )
    return table


def severity_tables(year: int, store_path: Path, raw_dir: Path) -> dict[str, list[dict]]:
    """Return the tables of the severity for one fused year."""
    detections, pairs, fires, _ = prepare(year, store_path, raw_dir)
    # The newest land cover that exists at the time of an alert is the map of the year before.
    layers = severity.load_layers(raw_dir, severity.cover_year(year))
    merges = load_merges(sqlite3.connect(store_path), year)
    rows = alert_rows(detections, merges, outcomes(detections, pairs, fires), layers)
    if year == config.DEVELOPMENT_YEAR and config.SEVERITY_POWER_STEPS_MW is None:
        return {"severity_inputs": inputs_table(rows)}
    tables = {"severity": score_table(rows), "severity_rank": rank_table(rows)}
    if year == config.DEVELOPMENT_YEAR:
        tables["severity_inputs"] = inputs_table(rows)
    return tables
