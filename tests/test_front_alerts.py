"""Tests of the first alerts that have a front, with cases small enough for paper."""

import sqlite3
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from chispa import fronts
from chispa.evaluation import front_alerts
from chispa.store import open_store, to_text

LAT, LON = -19.0, -57.0
EAST = 1 / (111_320 * np.cos(np.deg2rad(19.0)))  # One metre east in degrees, at the box centre.
HOUR = 3600.0
ALERT = 1_700_000_000.0  # The time of the alert, in seconds.


@pytest.fixture(autouse=True)
def fixed_values(monkeypatch):
    monkeypatch.setattr("chispa.config.LOOK_GAP", timedelta(hours=3))
    monkeypatch.setattr("chispa.config.FRONT_LINK_M", 1500.0)
    monkeypatch.setattr("chispa.config.FRONT_MIN_PIXELS", 3)
    monkeypatch.setattr("chispa.config.FRONT_ALERT_DELAYS_H", (0.5, 3, 6))


def pixels_of(rows: list[tuple]) -> np.ndarray:
    """Pixels on one line to the east: (issued id, observed, available, metres east)."""
    found = [(issued, seen, known, LAT, LON + east * EAST) for issued, seen, known, east in rows]
    return np.array(sorted(found), dtype=float)


def points_of(east_m: list[float]) -> np.ndarray:
    return fronts.metres(np.full(len(east_m), LAT), LON + np.array(east_m) * EAST)


def test_the_largest_front_has_the_pixels_that_a_chain_links():
    seen = np.full(3, ALERT)
    assert front_alerts.largest_front(seen[:0], points_of([])) == 0
    assert front_alerts.largest_front(seen[:2], points_of([0.0, 400.0])) == 2
    assert front_alerts.largest_front(seen, points_of([0.0, 400.0, 800.0])) == 3
    # The third pixel is 5 km from the others: no chain links the three.
    assert front_alerts.largest_front(seen, points_of([0.0, 400.0, 5400.0])) == 2


def test_only_the_newest_look_counts():
    # Three linked pixels in the first look, and one pixel in a look 12 hours later.
    seen = np.array([ALERT, ALERT, ALERT, ALERT + 12 * HOUR])
    assert front_alerts.largest_front(seen, points_of([0.0, 400.0, 800.0, 1200.0])) == 1


def test_a_front_counts_from_the_time_its_pixels_were_available():
    # GOES gave the alert. A VIIRS pass of one hour before it was available 2 hours after it.
    pixels = pixels_of([(1, ALERT - HOUR, ALERT + 2 * HOUR, east) for east in (0.0, 400.0, 800.0)])
    sizes = front_alerts.front_sizes([(1, ALERT)], pixels, [])
    assert sizes.tolist() == [[0, 3, 3]]


def test_the_pixels_of_a_second_event_count_only_after_the_merge():
    # The event 2 has a front from the start. The event 1 absorbs it 5 hours after the alert.
    pixels = pixels_of([(2, ALERT, ALERT + 0.1 * HOUR, east) for east in (0.0, 400.0, 800.0)])
    merges = [(ALERT + 5 * HOUR, 2, 1)]
    sizes = front_alerts.front_sizes([(1, ALERT)], pixels, merges)
    assert sizes.tolist() == [[0, 0, 3]]


def add(store: sqlite3.Connection, number: int, issued: int, row: tuple) -> None:
    """Add one detection (family, hours after the alert time, metres north) of an issued id."""
    family, hours, north_m = row
    when = to_text(datetime.fromtimestamp(ALERT + hours * HOUR, UTC))
    place = (LAT + north_m / 110_574, LON)
    values = (number, "firms", family, "any", when, when, *place, 375.0, 5.0, "nominal", 1)
    store.execute("INSERT INTO detections VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", values)
    # After a merge, the event of the detection is the event 1. Its issued id stays.
    store.execute("INSERT INTO memberships VALUES (?, 1, 'MEDIUM', ?)", (number, issued))


def test_a_first_alert_is_an_event_as_it_was_issued(tmp_path):
    # The id 1 starts with one GOES pixel, and gets a VIIRS pixel 2 km to the north 3 hours later.
    # The id 2 starts with two VIIRS pixels one hour later. A merge puts it into the event 1.
    store = open_store(tmp_path / "store.sqlite")
    rows = [
        (1, ("abi", 0, 0.0)),
        (1, ("viirs", 3, 2000.0)),
        (2, ("viirs", 1, 0.0)),
        (2, ("viirs", 1, 1000.0)),
    ]
    for number, (issued, row) in enumerate(rows, start=1):
        add(store, number, issued, row)
    first, second = sorted(store.execute(front_alerts.ALERTS, (0, 10)).fetchall())
    # Each issued id is one alert, with the time, the family and the place of its first moment.
    assert (first[0], first[1], first[2]) == (1, ALERT, "abi")
    assert (round(first[3], 6), first[4]) == (LAT, LON)
    assert (second[0], second[1], second[2]) == (2, ALERT + HOUR, "viirs")
    assert round(second[3], 6) == round(LAT + 500 / 110_574, 6)
