"""Tests of the steps of an event, with cases small enough for paper."""

import numpy as np

from chispa import growth
from chispa.evaluation.growth import step_table

M = 1 / 110_574  # one metre north, in degrees, at the equator


def test_detections_of_one_platform_near_in_time_are_one_pass():
    platform = np.array(["SNPP", "NOAA20", "SNPP", "SNPP", "NOAA20"])
    observed = np.array([100.0, 3100.0, 160.0, 40000.0, 3160.0])  # seconds
    assert growth.passes(platform, observed).tolist() == [0, 1, 0, 2, 1]


def test_step_gives_the_advance_the_new_pixels_and_the_direction(monkeypatch):
    monkeypatch.setattr("chispa.config.GROWTH_FLOOR_M", 500.0)
    monkeypatch.setattr("chispa.config.GROWTH_ADVANCE_PERCENT", 100)
    monkeypatch.setattr("chispa.config.GROWTH_SPEED_MIN_H", 6.0)
    # Pass 0: one pixel. Pass 1, ten hours later: one pixel 100 m north and one pixel 1000 m north.
    lat = np.array([0.0, 100 * M, 1000 * M])
    lon = np.zeros(3)
    (step,) = growth.steps(lat, lon, np.array([0, 1, 1]), np.array([0.0, 36000.0, 36000.0]))
    assert (step["hours"], step["pixels"], step["new_pixels"]) == (10.0, 2, 1)
    assert (round(step["advance_m"]), round(step["direction_deg"])) == (1000, 0)
    assert round(step["speed_m_h"]) == 100


def test_step_with_a_short_time_has_no_speed(monkeypatch):
    monkeypatch.setattr("chispa.config.GROWTH_FLOOR_M", 500.0)
    monkeypatch.setattr("chispa.config.GROWTH_SPEED_MIN_H", 6.0)
    lat, lon = np.array([0.0, 1000 * M]), np.zeros(2)
    (step,) = growth.steps(lat, lon, np.array([0, 1]), np.array([0.0, 3600.0]))
    assert (step["new_pixels"], step["speed_m_h"]) == (1, None)


def test_step_with_no_pixel_past_the_floor_has_no_direction(monkeypatch):
    monkeypatch.setattr("chispa.config.GROWTH_FLOOR_M", 500.0)
    lat, lon = np.array([0.0, 100 * M]), np.zeros(2)
    (step,) = growth.steps(lat, lon, np.array([0, 1]), np.array([0.0, 3600.0]))
    assert (step["new_pixels"], step["direction_deg"], step["speed_m_h"]) == (0, None, None)


def test_step_table_gives_the_speed_of_the_steps_with_a_new_pixel(monkeypatch):
    monkeypatch.setattr("chispa.config.GROWTH_HOUR_CLASSES", (0.0, 2.0, 24.0))
    monkeypatch.setattr("chispa.config.GROWTH_FLOOR_M", 500.0)
    steps = [
        {"hours": 1.0, "advance_m": 200.0, "new_pixels": 0, "speed_m_h": None, "empty_pass": False},
        {
            "hours": 10.0,
            "advance_m": 2000.0,
            "new_pixels": 3,
            "speed_m_h": 200.0,
            "empty_pass": True,
        },
        {
            "hours": 12.0,
            "advance_m": 600.0,
            "new_pixels": 1,
            "speed_m_h": 50.0,
            "empty_pass": False,
        },
    ]
    short, long, everything = step_table(steps)
    assert (short["steps"], short["advance_m_median"], short["steps_with_new_pixels"]) == (
        1,
        200.0,
        0,
    )
    assert (long["steps"], long["advance_m_median"], long["new_pixel_share"]) == (2, 1300.0, 1.0)
    assert (long["speed_m_h_median"], long["steps_after_empty_pass"]) == (125.0, 1)
    assert everything["steps"] == 3
