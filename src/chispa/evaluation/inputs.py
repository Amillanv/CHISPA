"""The inputs of the evaluation: the fused detections and the fires of one year, as arrays.

Each table reads the same arrays. Thus all tables use the same detections and the same fires.
"""

import sqlite3

import numpy as np

from chispa import config
from chispa.evaluation.match import Fields
from chispa.models import Fire
from chispa.store import read_fires

QUERY = """
SELECT d.source, d.sensor_family, m.level, d.platform, m.event_id,
       CAST(strftime('%s', d.observed_at) AS INTEGER),
       CAST(strftime('%s', d.available_at) AS INTEGER),
       CAST(substr(d.observed_at, 6, 2) AS INTEGER),
       CAST(strftime('%j', d.observed_at) AS INTEGER), d.lat, d.lon, d.footprint_m, d.frp_mw,
       d.source_confidence = 'high', m.issued_id
FROM detections d JOIN memberships m ON m.detection_id = d.id
WHERE m.event_id >= ? AND m.event_id < ?
"""
TEXT = ("source", "family", "level", "platform")
NUMBERS = (
    "event",
    "observed",
    "available",
    "month",
    "day",
    "lat",
    "lon",
    "footprint_m",
    "frp_mw",
    "high",
    "issued",
)


def load_detections(store: sqlite3.Connection, year: int) -> Fields:
    """Return the detections of one fused year as one array for each field."""
    first_id = year * 10_000_000
    cursor = store.execute(QUERY, (first_id, first_id + 10_000_000))
    parts: dict[str, list] = {name: [] for name in TEXT + NUMBERS}
    while chunk := cursor.fetchmany(200_000):
        columns = list(zip(*chunk, strict=True))
        for name, column in zip(TEXT + NUMBERS, columns, strict=True):
            # A detection with no fire power has None. In an array of numbers it is NaN.
            parts[name].append(np.array(column, dtype=float if name == "frp_mw" else None))
    if not parts["lat"]:
        raise RuntimeError(f"The store has no fusion results for {year}. Run `chispa fuse` first.")
    return {name: np.concatenate(chunks) for name, chunks in parts.items()}


def load_fires(store: sqlite3.Connection, year: int) -> Fields:
    """Return the fire fields as arrays, with the fire number as the index.

    Index 0 is "no fire". `counted` marks the fires that fire recall counts.
    A fire with no burn day has 0 in `first_day` and `last_day`, and its map month in `month`.
    """
    return fire_fields(read_fires(store, year), year)


def fire_fields(found: list[Fire], year: int) -> Fields:
    """Return the fields of the fires of one map year, in number sequence, as arrays."""
    area = np.array([0.0] + [fire.area_ha for fire in found])
    return {
        "area_ha": area,
        "month": np.array([0] + [fire.month or 0 for fire in found]),
        "first_day": np.array([0] + [fire.first_burn_day or 0 for fire in found]),
        "last_day": np.array([0] + [fire.last_burn_day or 0 for fire in found]),
        "counted": area >= config.EVAL_MIN_FIRE_HA,
        "year": year,
    }


def size_classes(fires: Fields) -> list[tuple[str, np.ndarray]]:
    """Return each fire size class as a label and a selection of fires."""
    limits = (*config.EVAL_SIZE_CLASSES_HA, np.inf)
    area = fires["area_ha"]
    return [
        (f"{low:g} to {high:g}", (area >= low) & (area < high))
        for low, high in zip(limits[:-1], limits[1:], strict=True)
    ]
