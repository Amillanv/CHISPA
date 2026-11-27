"""Tests of the first alerts that have a front, with cases small enough for paper."""

from datetime import timedelta

import numpy as np
import pytest

from chispa import fronts
from chispa.evaluation import front_alerts

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


def test_two_pixels_are_not_a_front_and_three_linked_pixels_are():
    seen = np.full(3, ALERT)
    assert not front_alerts.has_front(seen[:2], points_of([0.0, 400.0]))
    assert front_alerts.has_front(seen, points_of([0.0, 400.0, 800.0]))
    # The third pixel is 5 km from the others: no chain links the three.
    assert not front_alerts.has_front(seen, points_of([0.0, 400.0, 5400.0]))


def test_only_the_newest_look_counts():
    # Three linked pixels in the first look, and one pixel in a look 12 hours later.
    seen = np.array([ALERT, ALERT, ALERT, ALERT + 12 * HOUR])
    assert not front_alerts.has_front(seen, points_of([0.0, 400.0, 800.0, 1200.0]))


def test_a_front_counts_from_the_time_its_pixels_were_available():
    # GOES gave the alert. A VIIRS pass of one hour before it was available 2 hours after it.
    pixels = pixels_of([(1, ALERT - HOUR, ALERT + 2 * HOUR, east) for east in (0.0, 400.0, 800.0)])
    flags = front_alerts.front_flags([(1, ALERT)], pixels, [])
    assert flags.tolist() == [[False, True, True]]


def test_the_pixels_of_a_second_event_count_only_after_the_merge():
    # The event 2 has a front from the start. The event 1 absorbs it 5 hours after the alert.
    pixels = pixels_of([(2, ALERT, ALERT + 0.1 * HOUR, east) for east in (0.0, 400.0, 800.0)])
    merges = [(ALERT + 5 * HOUR, 2, 1)]
    flags = front_alerts.front_flags([(1, ALERT)], pixels, merges)
    assert flags.tolist() == [[False, False, True]]
