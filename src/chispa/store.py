"""The SQLite store: one file that holds all detections.

A database file lets each step read the result of the step before it.
SQLite is part of Python, thus the store adds no dependency and no server.
"""

import sqlite3
from dataclasses import astuple, fields
from datetime import UTC, datetime
from pathlib import Path

from chispa.models import Detection

SCHEMA = """
CREATE TABLE IF NOT EXISTS detections (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    sensor_family TEXT NOT NULL,
    platform TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    available_at TEXT NOT NULL,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    footprint_m REAL NOT NULL,
    frp_mw REAL,
    source_confidence TEXT NOT NULL,
    UNIQUE (source, platform, observed_at, lat, lon)
);
CREATE INDEX IF NOT EXISTS detections_available_at ON detections (available_at);
"""

COLUMNS = ", ".join(field.name for field in fields(Detection))
PLACEHOLDERS = ", ".join("?" for _ in fields(Detection))


def to_text(time: datetime) -> str:
    """Return a time as UTC text. All times in the store have this one format."""
    return time.astimezone(UTC).isoformat(timespec="seconds")


def open_store(path: Path) -> sqlite3.Connection:
    """Open the store file and make the tables if they are absent."""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)
    return connection


def add_detections(connection: sqlite3.Connection, detections: list[Detection]) -> int:
    """Save detections and return the number of new rows.

    The store ignores a detection that it already holds.
    Thus a second run of the same download does not make duplicates.
    """
    rows = [_to_row(detection) for detection in detections]
    before = connection.total_changes
    connection.executemany(
        f"INSERT OR IGNORE INTO detections ({COLUMNS}) VALUES ({PLACEHOLDERS})", rows
    )
    connection.commit()
    return connection.total_changes - before


def read_detections(
    connection: sqlite3.Connection, start: datetime, end: datetime
) -> list[Detection]:
    """Return detections with start <= available_at < end, in available_at sequence."""
    cursor = connection.execute(
        f"SELECT {COLUMNS} FROM detections WHERE available_at >= ? AND available_at < ? "
        "ORDER BY available_at, id",
        (to_text(start), to_text(end)),
    )
    return [_from_row(row) for row in cursor]


def _to_row(detection: Detection) -> tuple:
    row = list(astuple(detection))
    row[3], row[4] = to_text(detection.observed_at), to_text(detection.available_at)
    return tuple(row)


def _from_row(row: tuple) -> Detection:
    values = list(row)
    values[3], values[4] = datetime.fromisoformat(row[3]), datetime.fromisoformat(row[4])
    return Detection(*values)
