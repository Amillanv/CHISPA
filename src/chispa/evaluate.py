"""The evaluation: compare detections and alerts with the mapped burn scars.

For each scar we ask: did a detection fall on it, and when did the first one come?
We ask the same question for each source alone and for the merged alerts.
The fusion never reads this module or the scars. The evaluation runs after the fusion.
"""

import sqlite3
from collections import Counter
from pathlib import Path

import numpy as np

from chispa import config
from chispa.fusion import LEVELS
from chispa.grid import Grid, pantanal_grid
from chispa.sources import border
from chispa.store import read_scars

QUERY = """
SELECT d.source, d.sensor_family, m.level, m.event_id,
       CAST(strftime('%s', d.observed_at) AS INTEGER),
       CAST(strftime('%s', d.available_at) AS INTEGER),
       CAST(substr(d.observed_at, 6, 2) AS INTEGER),
       CAST(strftime('%j', d.observed_at) AS INTEGER), d.lat, d.lon, d.footprint_m
FROM detections d JOIN memberships m ON m.detection_id = d.id
WHERE m.event_id >= ? AND m.event_id < ?
"""
TEXT = ("source", "family", "level")
NUMBERS = ("event", "observed", "available", "month", "day", "lat", "lon", "footprint_m")


def load_detections(store: sqlite3.Connection, year: int) -> dict[str, np.ndarray]:
    """Return the detections of one fused year as one array for each field."""
    first_id = year * 10_000_000
    cursor = store.execute(QUERY, (first_id, first_id + 10_000_000))
    parts: dict[str, list] = {name: [] for name in TEXT + NUMBERS}
    while chunk := cursor.fetchmany(200_000):
        columns = list(zip(*chunk, strict=True))
        for name, column in zip(TEXT + NUMBERS, columns, strict=True):
            parts[name].append(np.array(column))
    if not parts["lat"]:
        raise RuntimeError(f"The store has no fusion results for {year}. Run `chispa fuse` first.")
    return {name: np.concatenate(chunks) for name, chunks in parts.items()}


def near_in_time(
    scars: dict[str, np.ndarray], found: np.ndarray, month: int, day: int
) -> np.ndarray:
    """Return True for each scar number in `found` that burned near the time of a detection.

    A scar with burn days: the day of the detection is in the burn days, plus the day margin.
    A scar with no burn day: the detection is in the scar month or in the months before it.
    """
    first, last = scars["first_day"][found], scars["last_day"][found]
    by_day = (day >= first - config.EVAL_DAY_MARGIN) & (day <= last + config.EVAL_DAY_MARGIN)
    months_before = scars["month"][found] - month
    by_month = (months_before >= 0) & (months_before <= config.EVAL_MONTHS_BEFORE)
    return np.where(first > 0, by_day, by_month)


def match(
    detections: dict[str, np.ndarray], numbers: np.ndarray, grid: Grid, scars: dict[str, np.ndarray]
) -> tuple[np.ndarray, np.ndarray]:
    """Return pairs (detection index, scar number) for each detection that matches a scar.

    A detection matches a scar if a pixel of the scar is in the square of the footprint
    plus the margin, and the scar burned near the time of the detection.
    """
    reach_m = detections["footprint_m"] + config.EVAL_MARGIN_M
    d_rows = np.ceil(reach_m / (grid.pixel_deg * 110_574)).astype(int)
    d_cols = np.ceil(
        reach_m / (grid.pixel_deg * 111_320 * np.cos(np.deg2rad(detections["lat"])))
    ).astype(int)
    rows, cols = grid.rows_cols(detections["lat"], detections["lon"])
    months, days = detections["month"], detections["day"]
    pair_detection, pair_scar = [], []
    for i in range(len(rows)):
        window = numbers[
            max(rows[i] - d_rows[i], 0) : rows[i] + d_rows[i] + 1,
            max(cols[i] - d_cols[i], 0) : cols[i] + d_cols[i] + 1,
        ]
        if not window.any():
            continue
        found = np.unique(window)
        found = found[found > 0]
        found = found[near_in_time(scars, found, months[i], days[i])]
        pair_detection += [i] * len(found)
        pair_scar += found.tolist()
    return np.array(pair_detection, dtype=int), np.array(pair_scar, dtype=int)


def first_times(pairs, chosen: np.ndarray, times: np.ndarray, scar_count: int) -> np.ndarray:
    """Return, for each scar number, the first time of a chosen detection that matches it.

    A scar with no chosen detection gets infinity.
    """
    pair_detection, pair_scar = pairs
    keep = chosen[pair_detection]
    first = np.full(scar_count + 1, np.inf)
    np.minimum.at(first, pair_scar[keep], times[pair_detection[keep]])
    return first


def measure(name, chosen, detections, pairs, scars, reference) -> dict:
    """Return the measures of one configuration: one subset of the detections.

    `scars` holds `area_ha` and `counted` for each scar number.
    `reference` holds the first observed and available time of each scar from all detections.
    """
    count = len(scars["area_ha"]) - 1
    observed = first_times(pairs, chosen, detections["observed"], count)
    available = first_times(pairs, chosen, detections["available"], count)
    found = np.isfinite(observed) & scars["counted"]
    matched = np.zeros(len(chosen), dtype=bool)
    matched[pairs[0]] = True
    delay_observed = (observed[found] - reference[0][found]) / 3600
    delay_available = (available[found] - reference[1][found]) / 3600
    return {
        "configuration": name,
        "detections": int(chosen.sum()),
        "unmatched_detections": int((chosen & ~matched).sum()),
        "unmatched_share": _share((chosen & ~matched).sum(), chosen.sum()),
        "scars": int(scars["counted"].sum()),
        "scars_found": int(found.sum()),
        "scar_recall": _share(found.sum(), scars["counted"].sum()),
        "area_recall": _share(
            scars["area_ha"][found].sum(), scars["area_ha"][scars["counted"]].sum()
        ),
        "delay_observed_h_median": _percentile(delay_observed, 50),
        "delay_observed_h_p90": _percentile(delay_observed, 90),
        "delay_available_h_median": _percentile(delay_available, 50),
        "delay_available_h_p90": _percentile(delay_available, 90),
    }


def _share(part, total) -> float | None:
    return round(float(part) / float(total), 4) if total else None


def _percentile(values: np.ndarray, percent: int) -> float | None:
    return round(float(np.percentile(values, percent)), 2) if len(values) else None


def configurations(detections: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Return each configuration as a selection of detections.

    A merged row selects the detections whose event had that level, or a higher level,
    immediately after the detection. Thus it shows what a brigade could know at that time.
    """
    chosen = {}
    for source in np.unique(detections["source"]):
        chosen[f"source {source}"] = detections["source"] == source
    for family in np.unique(detections["family"]):
        chosen[f"family {family}"] = detections["family"] == family
    rank = np.array([LEVELS.index(level) for level in LEVELS])
    level_rank = np.select([detections["level"] == level for level in LEVELS], rank)
    chosen["merged, level LOW or higher"] = level_rank >= 0
    chosen["merged, level MEDIUM or higher"] = level_rank >= 1
    chosen["merged, level HIGH"] = level_rank >= 2
    return chosen


def event_table(
    detections: dict[str, np.ndarray], pairs, final_level: dict[int, str]
) -> list[dict]:
    """Return, for each final level, how many events have a detection that matches a scar."""
    matched = np.zeros(len(detections["event"]), dtype=bool)
    matched[pairs[0]] = True
    events = np.unique(detections["event"])
    matched_events = set(np.unique(detections["event"][matched]).tolist())
    event_scar = set(zip(detections["event"][pairs[0]].tolist(), pairs[1].tolist(), strict=True))
    scars_of = Counter(event for event, _ in event_scar)
    rows = []
    for level in LEVELS:
        of_level = [event for event in events.tolist() if final_level[event] == level]
        hits = [event for event in of_level if event in matched_events]
        per_event = [scars_of[event] for event in hits]
        rows.append(
            {
                "final_level": level,
                "events": len(of_level),
                "events_matched": len(hits),
                "matched_share": _share(len(hits), len(of_level)),
                "scars_per_matched_event_median": _percentile(np.array(per_event), 50),
                "scars_per_matched_event_max": max(per_event, default=None),
            }
        )
    return rows


def size_table(detections, pairs, scars, chosen: dict[str, np.ndarray]) -> list[dict]:
    """Return the scar recall of each configuration for each scar size class."""
    limits = (*config.EVAL_SIZE_CLASSES_HA, np.inf)
    count = len(scars["area_ha"]) - 1
    rows = []
    for name, selection in chosen.items():
        found = np.isfinite(first_times(pairs, selection, detections["observed"], count))
        for low, high in zip(limits[:-1], limits[1:], strict=True):
            in_class = (scars["area_ha"] >= low) & (scars["area_ha"] < high) & scars["in_year"]
            rows.append(
                {
                    "configuration": name,
                    "size_class_ha": f"{low:g} to {high:g}",
                    "scars": int(in_class.sum()),
                    "scars_with_burn_day": int((in_class & (scars["first_day"] > 0)).sum()),
                    "scars_found": int((found & in_class).sum()),
                    "scar_recall": _share((found & in_class).sum(), in_class.sum()),
                }
            )
    return rows


def load_scars(store: sqlite3.Connection, year: int) -> dict[str, np.ndarray]:
    """Return the scar fields as arrays, with the scar number as the index.

    Index 0 is "no scar". `counted` marks the scars that scar recall counts.
    A scar with no burn day has 0 in `first_day` and `last_day`.
    """
    found = read_scars(store, year)
    area = np.array([0.0] + [scar.area_ha for scar in found])
    in_year = np.arange(len(area)) > 0
    return {
        "area_ha": area,
        "month": np.array([0] + [scar.month for scar in found]),
        "first_day": np.array([0] + [scar.first_burn_day or 0 for scar in found]),
        "last_day": np.array([0] + [scar.last_burn_day or 0 for scar in found]),
        "in_year": in_year,
        "counted": in_year & (area >= config.EVAL_MIN_SCAR_HA),
    }


def evaluate(year: int, store_path: Path, raw_dir: Path) -> dict[str, list[dict]]:
    """Return the result tables of one fused year."""
    store = sqlite3.connect(store_path)
    grid = pantanal_grid()
    detections = load_detections(store, year)
    in_biome = border.rasterize(border.read_rings(raw_dir / "border" / "pantanal.geojson"), grid)
    rows, cols = grid.rows_cols(detections["lat"], detections["lon"])
    keep = in_biome[rows, cols]
    del in_biome
    detections = {name: values[keep] for name, values in detections.items()}
    numbers = np.load(store_path.parent / "scars" / f"numbers_{year}.npz")["numbers"]
    scars = load_scars(store, year)
    area = scars["area_ha"]
    pairs = match(detections, numbers, grid, scars)
    everything = np.ones(len(keep[keep]), dtype=bool)
    reference = (
        first_times(pairs, everything, detections["observed"], len(area) - 1),
        first_times(pairs, everything, detections["available"], len(area) - 1),
    )
    chosen = configurations(detections)
    final_level = dict(store.execute("SELECT id, level FROM events"))
    return {
        "configurations": [
            measure(name, selection, detections, pairs, scars, reference)
            for name, selection in chosen.items()
        ],
        "scar_sizes": size_table(detections, pairs, scars, chosen),
        "events": event_table(detections, pairs, final_level),
    }
