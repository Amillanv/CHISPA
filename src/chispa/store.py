"""The SQLite store: one file that holds the detections, the fires and the fusion results.

A database file lets each step read the result of the step before it.
SQLite is part of Python, thus the store adds no dependency and no server.
"""

import sqlite3
from dataclasses import astuple, fields
from datetime import UTC, datetime
from pathlib import Path

from chispa.models import Detection, Fire

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
    available_estimated INTEGER NOT NULL,
    UNIQUE (source, platform, observed_at, lat, lon)
);
CREATE INDEX IF NOT EXISTS detections_available_at ON detections (available_at);
CREATE TABLE IF NOT EXISTS fires (
    year INTEGER NOT NULL,
    number INTEGER NOT NULL,
    area_ha REAL NOT NULL,
    month INTEGER,
    first_burn_day INTEGER,
    last_burn_day INTEGER,
    PRIMARY KEY (year, number)
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    first_observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL,
    first_available_at TEXT NOT NULL,
    detections INTEGER NOT NULL,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    south REAL NOT NULL,
    west REAL NOT NULL,
    north REAL NOT NULL,
    east REAL NOT NULL,
    max_frp_mw REAL,
    level TEXT NOT NULL,
    families TEXT NOT NULL,
    passes INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS alerts (
    event_id INTEGER NOT NULL,
    at TEXT NOT NULL,
    level TEXT NOT NULL,
    families TEXT NOT NULL,
    passes INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS alerts_event ON alerts (event_id);
CREATE TABLE IF NOT EXISTS memberships (
    detection_id INTEGER PRIMARY KEY,
    event_id INTEGER NOT NULL,
    level TEXT NOT NULL,
    issued_id INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS memberships_event ON memberships (event_id);
CREATE INDEX IF NOT EXISTS memberships_issued ON memberships (issued_id);
CREATE TABLE IF NOT EXISTS merges (
    at TEXT NOT NULL,
    absorbed_id INTEGER NOT NULL,
    into_id INTEGER NOT NULL
);
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
    columns = [row[1] for row in connection.execute("PRAGMA table_info(detections)")]
    if "available_estimated" not in columns:
        raise RuntimeError(f"{path} is from an older version. Run `chispa build`, then `fuse`.")
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


def read_detections(connection: sqlite3.Connection, start: datetime, end: datetime):
    """Give (id, detection) with start <= available_at < end, in available_at sequence.

    This gives one record at a time. A year of detections does not fit well in memory.
    """
    cursor = connection.execute(
        f"SELECT id, {COLUMNS} FROM detections WHERE available_at >= ? AND available_at < ? "
        "ORDER BY available_at, id",
        (to_text(start), to_text(end)),
    )
    for row in cursor:
        yield row[0], _from_row(row[1:])


def replace_fusion(
    connection: sqlite3.Connection, id_range: tuple[int, int], fusion: tuple
) -> None:
    """Delete the fusion results with an event id in the range, then save the new results.

    `fusion` is what `fuse` returns: the events, the alert changes, the memberships and the merges.
    """
    events, alerts, memberships, merges = fusion
    tables = (
        ("events", "id"),
        ("alerts", "event_id"),
        ("memberships", "event_id"),
        ("merges", "into_id"),
    )
    for table, column in tables:
        connection.execute(f"DELETE FROM {table} WHERE {column} >= ? AND {column} < ?", id_range)
    rows = [_times_to_text(astuple(event), (1, 2, 3)) for event in events]
    connection.executemany(f"INSERT INTO events VALUES ({', '.join('?' * 15)})", rows)
    rows = [_times_to_text(astuple(alert), (1,)) for alert in alerts]
    connection.executemany("INSERT INTO alerts VALUES (?, ?, ?, ?, ?)", rows)
    connection.executemany("INSERT INTO memberships VALUES (?, ?, ?, ?)", memberships)
    rows = [_times_to_text(merge, (0,)) for merge in merges]
    connection.executemany("INSERT INTO merges VALUES (?, ?, ?)", rows)
    connection.commit()


def _times_to_text(row: tuple, positions: tuple[int, ...]) -> tuple:
    values = list(row)
    for position in positions:
        values[position] = to_text(values[position])
    return tuple(values)


def add_fires(connection: sqlite3.Connection, year: int, fires: list[Fire]) -> None:
    """Save the fires of one year."""
    connection.executemany(
        "INSERT INTO fires VALUES (?, ?, ?, ?, ?, ?)", [(year, *astuple(fire)) for fire in fires]
    )
    connection.commit()


def read_fires(connection: sqlite3.Connection, year: int) -> list[Fire]:
    """Return the fires of one year, in number sequence."""
    cursor = connection.execute(
        "SELECT number, area_ha, month, first_burn_day, last_burn_day FROM fires "
        "WHERE year = ? ORDER BY number",
        (year,),
    )
    return [Fire(*row) for row in cursor]


def _to_row(detection: Detection) -> tuple:
    row = list(astuple(detection))
    row[3], row[4] = to_text(detection.observed_at), to_text(detection.available_at)
    return tuple(row)


def _from_row(row: tuple) -> Detection:
    values = list(row)
    values[3], values[4] = datetime.fromisoformat(row[3]), datetime.fromisoformat(row[4])
    values[10] = bool(row[10])
    return Detection(*values)
