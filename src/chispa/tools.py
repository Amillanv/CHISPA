"""The tools: the functions that answer questions about alerts and results.

The MCP server, the agent and the dashboard contain no logic. They call these functions.
Each function has an as-of time. It uses only detections that were available at that time,
thus the same question about a moment in 2024 or about this minute gets an honest answer.
"""

import csv
import math
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from chispa import config
from chispa.store import to_text

NEAR = """
SELECT m.event_id, d.lat, d.lon
FROM detections d JOIN memberships m ON m.detection_id = d.id
WHERE d.available_at > ? AND d.available_at <= ?
  AND d.lat BETWEEN ? AND ? AND d.lon BETWEEN ? AND ?
"""
STATE = """
SELECT MAX(d.available_at), MIN(d.observed_at), MAX(d.observed_at), COUNT(*),
       MAX(d.frp_mw), GROUP_CONCAT(DISTINCT d.sensor_family)
FROM detections d JOIN memberships m ON m.detection_id = d.id
WHERE m.event_id = ? AND d.available_at <= ?
"""
# The level of an event at a time is the level after its newest detection at that time.
LEVEL = """
SELECT m.level FROM detections d JOIN memberships m ON m.detection_id = d.id
WHERE m.event_id = ? AND d.available_at <= ? ORDER BY d.available_at DESC, d.id DESC LIMIT 1
"""
NEWEST = """
SELECT d.lat, d.lon, d.observed_at, d.available_at, d.sensor_family, d.platform, d.source, d.frp_mw
FROM detections d JOIN memberships m ON m.detection_id = d.id
WHERE m.event_id = ? AND d.available_at <= ? ORDER BY d.observed_at DESC LIMIT ?
"""


def alerts_near(
    lat: float, lon: float, radius_km: float, since_hours: float, as_of: datetime
) -> list[dict]:
    """Return the events with a new detection near a position, the nearest event first.

    A detection is new if it became available in the `since_hours` before `as_of`.
    Each event has its confidence level at the time `as_of`.
    """
    _check(lat, lon, as_of)
    if not 0 < radius_km <= config.TOOL_MAX_RADIUS_KM or since_hours <= 0:
        raise ValueError(
            f"radius_km must be from 0 to {config.TOOL_MAX_RADIUS_KM}, and since_hours more than 0."
        )
    d_lat = radius_km / 110.574
    d_lon = radius_km / (111.320 * math.cos(math.radians(lat)))
    store = _open()
    start = as_of - timedelta(hours=since_hours)
    box = (lat - d_lat, lat + d_lat, lon - d_lon, lon + d_lon)
    near: dict[int, list] = {}
    for event_id, found_lat, found_lon in store.execute(
        NEAR, (to_text(start), to_text(as_of), *box)
    ):
        distance_km = _distance_km(lat, lon, found_lat, found_lon)
        if distance_km <= radius_km:
            near.setdefault(event_id, []).append((distance_km, found_lat, found_lon))
    events = []
    for event_id, found in near.items():
        distance_km, near_lat, near_lon = min(found)
        events.append(
            _state(store, event_id, as_of)
            | {
                "new_detections_near": len(found),
                "nearest_km": round(distance_km, 2),
                "nearest_lat": near_lat,
                "nearest_lon": near_lon,
            }
        )
    return sorted(events, key=lambda event: event["nearest_km"])


def event_detail(event_id: int, as_of: datetime) -> dict:
    """Return what was known about one event at the time `as_of`.

    The answer has the state of the event, each change of its alert, and its newest detections.
    """
    _check(0.0, 0.0, as_of)
    store = _open()
    state = _state(store, event_id, as_of)
    changes = store.execute(
        "SELECT at, level, families, passes FROM alerts WHERE event_id = ? AND at <= ? ORDER BY at",
        (event_id, to_text(as_of)),
    )
    names = ("lat", "lon", "observed_at", "available_at", "sensor_family", "platform", "source")
    newest = store.execute(NEWEST, (event_id, to_text(as_of), config.TOOL_MAX_DETECTIONS))
    return state | {
        "alert_changes": [
            dict(zip(("at", "level", "sensor_families", "passes"), row, strict=True))
            for row in changes
        ],
        "newest_detections": [dict(zip((*names, "frp_mw"), row, strict=True)) for row in newest],
    }


def evaluation_summary(year: int) -> dict:
    """Return the measured quality of the alerts for one evaluated year, with its limits.

    The numbers come from the result tables. This function calculates nothing.
    """
    folder = config.RESULTS_DIR / str(year)
    if not folder.is_dir():
        raise ValueError(f"There are no results for {year}. Run `chispa evaluate --year {year}`.")
    tables = {}
    for name in ("configurations", "events", "merge_gain"):
        with (folder / f"{name}.csv").open(newline="") as file:
            tables[name] = list(csv.DictReader(file))
    summary = (config.RESULTS_DIR / "SUMMARY.md").read_text()
    return {
        "year": year,
        "role": "test year" if year == config.TEST_YEAR else "development year",
        "sources": "satellites only",
        "configuration": tables["configurations"][0]["config"],
        "run_date": tables["configurations"][0]["run_date"],
        "limits": summary[summary.index("Limits of these results:") :].strip(),
        **tables,
    }


def _open() -> sqlite3.Connection:
    path: Path = config.STORE_PATH
    if not path.exists():
        raise RuntimeError(f"The store {path} does not exist. Run `chispa build` first.")
    return sqlite3.connect(path)


def _check(lat: float, lon: float, as_of: datetime) -> None:
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError(f"Position is not on the Earth: {lat}, {lon}.")
    if as_of.utcoffset() is None:
        raise ValueError("as_of has no timezone. Use a UTC time.")


def _distance_km(lat_1: float, lon_1: float, lat_2: float, lon_2: float) -> float:
    """Return the distance between two positions on a sphere (haversine formula)."""
    a_lat, b_lat = math.radians(lat_1), math.radians(lat_2)
    half = (
        math.sin((b_lat - a_lat) / 2) ** 2
        + math.cos(a_lat) * math.cos(b_lat) * math.sin(math.radians(lon_2 - lon_1) / 2) ** 2
    )
    return 6371.0 * 2 * math.asin(math.sqrt(half))


def _state(store: sqlite3.Connection, event_id: int, as_of: datetime) -> dict:
    """Return the state of one event from the detections that were available at `as_of`."""
    moment = (event_id, to_text(as_of))
    newest, first, last, count, max_frp_mw, families = store.execute(STATE, moment).fetchone()
    if not count:
        raise ValueError(f"The event {event_id} has no detection at {to_text(as_of)}.")
    level = store.execute(LEVEL, moment).fetchone()[0]
    age = as_of - datetime.fromisoformat(last)
    return {
        "event_id": event_id,
        "as_of": to_text(as_of),
        "level": level,
        "detections": count,
        "sensor_families": sorted(families.split(",")),
        "first_observed_at": first,
        "last_observed_at": last,
        "newest_available_at": newest,
        "newest_observation_age_h": round(age.total_seconds() / 3600, 2),
        "max_frp_mw": max_frp_mw,
    }
