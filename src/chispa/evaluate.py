"""The evaluation: compare detections and alerts with the mapped fires.

For each fire we ask: did a detection fall on it, and when did the first one come?
We ask the same question for each source alone and for the merged alerts.
The fusion never reads this module or the fires. The evaluation runs after the fusion.
"""

import sqlite3
from pathlib import Path

import numpy as np

from chispa import config
from chispa.fusion import LEVELS
from chispa.grid import pantanal_grid
from chispa.match import Fields, Pairs, first_times, isolated, match
from chispa.sources import border
from chispa.store import read_fires

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


def load_detections(store: sqlite3.Connection, year: int) -> Fields:
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


def measure(name: str, chosen: np.ndarray, detections: Fields, pairs: Pairs, fires: Fields) -> dict:
    """Return the measures of one configuration: one subset of the detections.

    A delay is the first time of the configuration minus the first time of all detections.
    Only isolated fires give a delay.
    """
    count = len(fires["area_ha"]) - 1
    counted = fires["counted"]
    everything = np.ones(len(chosen), dtype=bool)
    found = np.isfinite(first_times(pairs, chosen, detections["observed"], count)) & counted
    matched = np.zeros(len(chosen), dtype=bool)
    matched[pairs[0]] = True
    timed = found & fires["isolated"]
    row = {
        "configuration": name,
        "detections": int(chosen.sum()),
        "unmatched_detections": int((chosen & ~matched).sum()),
        "unmatched_share": _share((chosen & ~matched).sum(), chosen.sum()),
        "fires": int(counted.sum()),
        "fires_found": int(found.sum()),
        "fire_recall": _share(found.sum(), counted.sum()),
        "area_recall": _share(fires["area_ha"][found].sum(), fires["area_ha"][counted].sum()),
        "delay_fires": int(timed.sum()),
    }
    for time in ("observed", "available"):
        reference = first_times(pairs, everything, detections[time], count)[timed]
        delay_h = (first_times(pairs, chosen, detections[time], count)[timed] - reference) / 3600
        row[f"delay_{time}_h_median"] = _percentile(delay_h, 50)
        row[f"delay_{time}_h_p90"] = _percentile(delay_h, 90)
    return row


def _share(part: float, total: float) -> float | None:
    return round(float(part) / float(total), 4) if total else None


def _percentile(values: np.ndarray, percent: int) -> float | None:
    return round(float(np.percentile(values, percent)), 2) if len(values) else None


def configurations(detections: Fields) -> Fields:
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


def _links(detections: Fields, pairs: Pairs, fires: Fields) -> tuple[np.ndarray, ...]:
    """Return each different (event, counted fire) that a match connects, as three arrays:
    the event, the fire, and the number of matches between the two."""
    counted = fires["counted"][pairs[1]]
    both = np.stack([detections["event"][pairs[0][counted]], pairs[1][counted]])
    (events, numbers), matches = np.unique(both, axis=1, return_counts=True)
    return events, numbers, matches


def _main_share(group: np.ndarray, matches: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return, for each group number, all its matches and the matches of its largest link."""
    total = np.bincount(group, weights=matches)
    main = np.zeros(len(total))
    np.maximum.at(main, group, matches)
    return total, main


def event_table(detections: Fields, pairs: Pairs, fires: Fields, final_level: dict) -> list[dict]:
    """Return, for each final level, how many events match a fire and how many fires.

    `matched_share` is the precision against the map. `purity` is the share of the matches
    of an event that are on its main fire. A low purity shows that the fusion merged fires.
    """
    matched = np.zeros(len(detections["event"]), dtype=bool)
    matched[pairs[0]] = True
    matched_events = set(np.unique(detections["event"][matched]).tolist())
    link_event, _, matches = _links(detections, pairs, fires)
    on_fires, position = np.unique(link_event, return_inverse=True)
    total, main = _main_share(position, matches)
    fires_of = np.bincount(position)
    rows = []
    for level in (*LEVELS, "all"):
        of_level = [level == "all" or final_level[event] == level for event in on_fires.tolist()]
        events = [
            event
            for event in np.unique(detections["event"]).tolist()
            if level == "all" or final_level[event] == level
        ]
        hits = sum(event in matched_events for event in events)
        rows.append(
            {
                "final_level": level,
                "events": len(events),
                "events_matched": hits,
                "matched_share": _share(hits, len(events)),
                "events_on_counted_fires": sum(of_level),
                "events_on_one_fire": int((fires_of[of_level] == 1).sum()),
                "fires_per_event_max": int(fires_of[of_level].max()) if any(of_level) else None,
                "purity": _share(main[of_level].sum(), total[of_level].sum()),
            }
        )
    return rows


def _size_classes(fires: Fields) -> list[tuple[str, np.ndarray]]:
    limits = (*config.EVAL_SIZE_CLASSES_HA, np.inf)
    area = fires["area_ha"]
    return [
        (f"{low:g} to {high:g}", (area >= low) & (area < high))
        for low, high in zip(limits[:-1], limits[1:], strict=True)
    ]


def size_table(detections: Fields, pairs: Pairs, fires: Fields, chosen: Fields) -> list[dict]:
    """Return the fire recall of each configuration for each fire size class."""
    count = len(fires["area_ha"]) - 1
    rows = []
    for name, selection in chosen.items():
        found = np.isfinite(first_times(pairs, selection, detections["observed"], count))
        for label, in_class in _size_classes(fires):
            rows.append(
                {
                    "configuration": name,
                    "size_class_ha": label,
                    "fires": int(in_class.sum()),
                    "fires_found": int((found & in_class).sum()),
                    "fire_recall": _share((found & in_class).sum(), in_class.sum()),
                }
            )
    return rows


def split_table(detections: Fields, pairs: Pairs, fires: Fields) -> list[dict]:
    """Return, for each fire size class, into how many events the fusion split a fire.

    `completeness` is the share of the matches of a fire that are in its main event.
    """
    _, link_fire, matches = _links(detections, pairs, fires)
    count = len(fires["area_ha"])
    events_of = np.bincount(link_fire, minlength=count)
    total, main = (
        np.pad(values, (0, count - len(values))) for values in _main_share(link_fire, matches)
    )
    rows = []
    for label, in_class in (*_size_classes(fires), ("all", fires["counted"])):
        found = in_class & (events_of > 0)
        rows.append(
            {
                "size_class_ha": label,
                "fires": int(in_class.sum()),
                "fires_with_burn_day": int((in_class & (fires["first_day"] > 0)).sum()),
                "fires_isolated": int((in_class & fires["isolated"]).sum()),
                "fires_found": int(found.sum()),
                "fires_in_one_event": int((events_of[found] == 1).sum()),
                "events_per_fire_median": _percentile(events_of[found], 50),
                "events_per_fire_max": int(events_of[found].max()) if found.any() else None,
                "completeness": _share(main[found].sum(), total[found].sum()),
            }
        )
    return rows


def load_fires(store: sqlite3.Connection, year: int) -> Fields:
    """Return the fire fields as arrays, with the fire number as the index.

    Index 0 is "no fire". `counted` marks the fires that fire recall counts.
    A fire with no burn day has 0 in `first_day` and `last_day`, and its map month in `month`.
    """
    found = read_fires(store, year)
    area = np.array([0.0] + [fire.area_ha for fire in found])
    return {
        "area_ha": area,
        "month": np.array([0] + [fire.month or 0 for fire in found]),
        "first_day": np.array([0] + [fire.first_burn_day or 0 for fire in found]),
        "last_day": np.array([0] + [fire.last_burn_day or 0 for fire in found]),
        "counted": area >= config.EVAL_MIN_FIRE_HA,
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
    numbers = np.load(store_path.parent / "fires" / f"{year}.npz")["numbers"]
    fires = load_fires(store, year)
    pairs = match(detections, numbers, grid, fires)
    fires["isolated"] = isolated(pairs, fires)
    chosen = configurations(detections)
    final_level = dict(store.execute("SELECT id, level FROM events"))
    return {
        "configurations": [
            measure(name, selection, detections, pairs, fires) for name, selection in chosen.items()
        ],
        "fire_sizes": size_table(detections, pairs, fires, chosen),
        "fire_events": split_table(detections, pairs, fires),
        "events": event_table(detections, pairs, fires, final_level),
    }
