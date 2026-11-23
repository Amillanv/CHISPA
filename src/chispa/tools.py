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

from chispa import config, live, record, region
from chispa.store import to_text

NEAR = """
SELECT m.issued_id, d.lat, d.lon
FROM detections d JOIN memberships m ON m.detection_id = d.id
WHERE d.available_at > ? AND d.available_at <= ?
  AND d.lat BETWEEN ? AND ? AND d.lon BETWEEN ? AND ?
"""


def alerts_near(
    lat: float, lon: float, radius_km: float, since_hours: float, as_of: datetime
) -> list[dict]:
    """Return the events with a new detection near a position, the nearest event first.

    A detection is new if it became available in the `since_hours` before `as_of`.
    Each event is the event as it was at the time `as_of`, with its confidence level at that time.
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
    replay = record.replay_at(store, as_of)
    near: dict[int, list] = {}
    for issued_id, found_lat, found_lon in store.execute(
        NEAR, (to_text(start), to_text(as_of), *box)
    ):
        distance_km = _distance_km(lat, lon, found_lat, found_lon)
        if distance_km <= radius_km:
            event_id = replay.root(issued_id)
            near.setdefault(event_id, []).append((distance_km, found_lat, found_lon))
    events = []
    for event_id, found in near.items():
        distance_km, near_lat, near_lon = min(found)
        state = record.state(record.read(store, replay.ids(event_id), as_of), event_id, as_of)
        events.append(
            state
            | {
                "new_detections_near": len(found),
                "nearest_km": round(distance_km, 2),
                "nearest_lat": near_lat,
                "nearest_lon": near_lon,
            }
        )
    return sorted(events, key=lambda event: event["nearest_km"])


def event_record(event_id: int, as_of: datetime) -> dict:
    """Return all that CHISPA can say about one event at the time `as_of`.

    The answer has the state of the event, the rank of its confidence, its severity with its
    facts, its growth steps and what GOES examined. `record.py` gives each part.
    """
    _check(0.0, 0.0, as_of)
    return record.event_record(_open(), event_id, as_of, config.RAW_DIR)


def activity(hours: float, step_hours: float, as_of: datetime) -> dict:
    """Return the events and the detections in the Pantanal box for each step of a window.

    The window is the `hours` before `as_of`, in steps of `step_hours`, the oldest step first.
    An event counts in a step if a detection of it became available in that step, with the
    level after its newest detection of the step. The events are the events at `as_of`.
    `newest_observed_at` has the newest observation of each sensor family in the window.
    """
    _check(0.0, 0.0, as_of)
    step_s = step_hours * 3600
    count = hours * 3600 / step_s if step_s >= 1 else 0.0
    whole = _whole(step_s) and _whole(count)
    if not (whole and 1 <= round(count) <= config.TOOL_MAX_STEPS):
        raise ValueError(
            "step_hours must be a whole number of seconds, and hours a multiple of it, "
            f"with 1 to {config.TOOL_MAX_STEPS} steps."
        )
    return region.steps(_open(), config.PANTANAL_BOX, as_of, hours, step_hours)


def live_status(as_of: datetime) -> dict:
    """Return the newest pass of the poller at or before `as_of`, and the result of each source.

    The time from that pass to `as_of` says how old the live data is. With no pass at or before
    `as_of`, the store has archive data only, with an estimate of when each detection was available.
    """
    _check(0.0, 0.0, as_of)
    return {"as_of": to_text(as_of)} | live.last_pass(config.RAW_DIR, as_of)


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
        "role": config.YEAR_ROLES[year],
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


def _whole(value: float) -> bool:
    """Return True if a value is a whole number. A sum of hours in binary has a small error."""
    return abs(value - round(value)) < 1e-6


def _distance_km(lat_1: float, lon_1: float, lat_2: float, lon_2: float) -> float:
    """Return the distance between two positions on a sphere (haversine formula)."""
    a_lat, b_lat = math.radians(lat_1), math.radians(lat_2)
    half = (
        math.sin((b_lat - a_lat) / 2) ** 2
        + math.cos(a_lat) * math.cos(b_lat) * math.sin(math.radians(lon_2 - lon_1) / 2) ** 2
    )
    return 6371.0 * 2 * math.asin(math.sqrt(half))
