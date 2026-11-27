"""Tests of the fronts against the flames of Sentinel-2, with cases small enough for paper."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from chispa import fronts
from chispa.evaluation import flames

LAT, LON = -19.0, -57.0
EAST = 1 / (111_320 * np.cos(np.deg2rad(19.0)))  # One metre east in degrees, at the box centre.
START = datetime(2023, 9, 1, 5, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def fixed_values(monkeypatch):
    monkeypatch.setattr("chispa.config.FRONT_LINK_M", 1500.0)
    monkeypatch.setattr("chispa.config.FRONT_WINDOWS_H", {12: (6, 18), 24: (6, 30)})
    monkeypatch.setattr("chispa.config.FRONT_REACH_M", {12: 5000.0, 24: 8000.0})
    monkeypatch.setattr("chispa.config.GROWTH_FLOOR_M", 850.0)
    monkeypatch.setattr("chispa.config.FLAMES_MIN_HOT", 10)
    monkeypatch.setattr("chispa.config.FLAMES_MIN_CLEAR", 0.8)
    monkeypatch.setattr("chispa.config.ADVANCE_SAME_DEG", 45.0)


def front_of_three_pixels() -> tuple[fronts.Look, dict, dict]:
    """A front of three pixels in a row to the east, with the answer "new ground" to the east."""
    place = {"start": START.timestamp(), "lat": np.full(3, LAT)}
    place["lon"] = LON + np.array([0.0, 400.0, 800.0]) * EAST
    look = fronts.make_look(fronts.metres(place["lat"], place["lon"]), np.empty((0, 2)))
    answers = {}
    for hours in (12, 24):
        answers[f"answer_{hours}"] = np.array([0])
        answers[f"direction_deg_{hours}"] = np.array([90.0])
        answers[f"distance_m_{hours}"] = np.array([1300.0])
    return look, place, answers


def test_the_hot_pixels_of_the_image_get_the_rule_of_a_new_pixel(monkeypatch):
    look, place, answers = front_of_three_pixels()
    image = [("IMAGE", START + timedelta(hours=9), 0.9)]
    monkeypatch.setattr("chispa.sources.sentinel2.cloud_free_views", lambda box, first, last: image)
    # 5 hot pixels on the front, and 12 hot pixels from 1200 m to 1420 m east of its last pixel.
    east = np.concatenate([np.linspace(300, 500, 5), 800 + np.linspace(1200, 1420, 12)])
    hot = (np.full(len(east), LAT), LON + east * EAST)
    monkeypatch.setattr("chispa.sources.sentinel2.hot_pixels", lambda name, box: hot)
    row = flames.check_front(look, 0, place, answers)
    assert (row["hours"], row["image"], row["image_hours"]) == (12, "IMAGE", 9.0)
    assert (row["answer"], row["new_hot_pixels"]) == ("new_ground", 12)
    assert row["flames_direction_deg"] == 90.0
    # The 90th percentile of 12 equal steps from 1200 m to 1420 m is 1398 m.
    assert row["flames_distance_m"] == 1398.0


def test_a_front_with_no_image_in_its_windows_has_no_row(monkeypatch):
    look, place, answers = front_of_three_pixels()
    monkeypatch.setattr("chispa.sources.sentinel2.cloud_free_views", lambda box, first, last: [])
    assert flames.check_front(look, 0, place, answers) is None


def row_of(new_hot: int, answer: str, clear: float = 0.9, directions: tuple = ("", "")) -> dict:
    row = {"hours": "12", "new_hot_pixels": str(new_hot), "answer": answer, "clear_share": clear}
    row |= {"direction_deg": directions[0], "flames_direction_deg": directions[1]}
    return row | {"distance_m": "1500.0", "flames_distance_m": "1200.0"}


def test_the_table_compares_the_two_answers():
    rows = [
        row_of(25, "new_ground", directions=("90.0", "100.0")),
        row_of(12, "front_again"),
        row_of(15, "not_visible"),
        row_of(0, "clear_no_fire"),
        row_of(0, "new_ground", directions=("10.0", "")),
        row_of(0, "front_again", clear=0.3),  # Cloud: the image has no answer.
        row_of(4, "front_again"),  # Less than the minimum of hot pixels: no group.
    ]
    first, second = flames.table(rows)
    assert (first["hours"], first["fronts_with_image"]) == (12, 7)
    assert (first["flames_on_new_ground"], first["of_them_new_ground"]) == (3, 1)
    assert (first["share_of_them"], first["of_them_not_visible"]) == (round(1 / 3, 4), 1)
    assert (first["no_flames_on_new_ground"], first["of_those_new_ground"]) == (2, 1)
    assert (first["directions_in_45"], first["directions_compared"]) == (1, 1)
    assert (first["distance_m_median"], first["flames_distance_m_median"]) == (1500.0, 1200.0)
    assert (second["hours"], second["fronts_with_image"], second["share_of_them"]) == (24, 0, None)
