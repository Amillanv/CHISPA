"""Tests of the fronts and their answers, with cases small enough for paper."""

from datetime import timedelta

import numpy as np
import pytest

from chispa import fronts


@pytest.fixture(autouse=True)
def fixed_values(monkeypatch):
    monkeypatch.setattr("chispa.config.LOOK_GAP", timedelta(hours=3))
    monkeypatch.setattr("chispa.config.FRONT_LINK_M", 1500.0)
    monkeypatch.setattr("chispa.config.FRONT_REACH_M", {12: 5000.0, 24: 8000.0})
    monkeypatch.setattr("chispa.config.FRONT_SECTORS", 8)
    monkeypatch.setattr("chispa.config.GROWTH_FLOOR_M", 850.0)
    monkeypatch.setattr("chispa.config.GROWTH_ADVANCE_PERCENT", 90)


def test_detections_with_no_long_gap_are_one_look():
    hour = 3600.0
    observed = np.array([0.0, 600.0, 5 * hour, 5 * hour + 600, 300.0])
    assert fronts.looks(observed).tolist() == [0, 0, 1, 1, 0]


def test_a_chain_of_pixels_is_one_front():
    # Metres north, metres east. The gaps are 1000 m, 1400 m and 7600 m: the link is 1500 m.
    points = np.array([[0.0, 0.0], [0.0, 1000.0], [0.0, 2400.0], [0.0, 10_000.0]])
    assert fronts.fronts(points).tolist() == [0, 0, 0, 1]


def test_sector_0_has_north_at_its_centre_and_the_numbers_go_clockwise():
    lines = np.array([[1.0, 0.0], [0.0, 1.0], [-1.0, -1.0], [1.0, -0.1]])
    assert fronts.sector(lines).tolist() == [0, 2, 5, 0]


def test_one_degree_of_latitude_is_110_574_metres():
    assert fronts.metres(np.array([1.0]), np.array([0.0])).tolist() == [[110_574.0, 0.0]]


def test_answers_give_the_new_pixels_of_each_front_and_their_sector():
    # Front 0: three pixels in a row to the east. Front 1: one pixel 20 km to the east.
    points = np.array([[0.0, 0.0], [0.0, 400.0], [0.0, 800.0], [0.0, 20_000.0]])
    before = np.array([[3000.0, 800.0]])  # A pixel that we knew, 3 km north of the row.
    look = fronts.make_look(points, before)
    assert look.labels.tolist() == [0, 0, 0, 1]
    later = np.array(
        [
            [0.0, 2000.0],  # 1200 m east of front 0: new.
            [0.0, 3000.0],  # 2200 m east of front 0: new.
            [300.0, 400.0],  # 300 m from front 0: the front again, not new.
            [3000.0, 1500.0],  # 700 m from the known pixel: not new.
            [0.0, 12_000.0],  # 8 km from the nearest pixel of the look: not in the reach.
            [-1000.0, 20_000.0],  # 1000 m south of front 1: new.
        ]
    )
    found = fronts.answers(look, later, 5000.0)
    assert found["again"].tolist() == [1, 0]
    assert found["new"].tolist() == [2, 1]
    assert found["sectors"].tolist() == [[0, 0, 2, 0, 0, 0, 0, 0], [0, 0, 0, 0, 1, 0, 0, 0]]
    assert found["direction_deg"].tolist() == [90.0, 180.0]
    # The 90th percentile of 1200 m and 2200 m is 2100 m.
    assert found["distance_m"].tolist() == pytest.approx([2100.0, 1000.0])


def test_a_front_with_no_later_pixel_has_no_direction_and_no_distance():
    look = fronts.make_look(np.array([[0.0, 0.0], [0.0, 500.0], [0.0, 1000.0]]), np.empty((0, 2)))
    found = fronts.answers(look, np.empty((0, 2)), 5000.0)
    assert (found["again"].tolist(), found["new"].tolist()) == ([0], [0])
    assert np.isnan(found["direction_deg"]).all() and np.isnan(found["distance_m"]).all()
