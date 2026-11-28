"""Tests of the answers of a front, with cases small enough for paper."""

from datetime import UTC, date, datetime, timedelta

import numpy as np
import pytest
from scipy.spatial import cKDTree

from chispa import fronts
from chispa.evaluation import fronts as steps
from chispa.grid import pantanal_grid

LAT, LON = -19.0, -57.0
EAST = 1 / (111_320 * np.cos(np.deg2rad(19.0)))  # One metre east in degrees, at the box centre.
START = datetime(2023, 9, 1, 5, 0, tzinfo=UTC).timestamp()
HOUR = 3600.0
SEEN, CLOUD, BLOCKED = 1, 0, 2


@pytest.fixture(autouse=True)
def fixed_values(monkeypatch):
    monkeypatch.setattr("chispa.config.LOOK_GAP", timedelta(hours=3))
    monkeypatch.setattr("chispa.config.FRONT_LINK_M", 1500.0)
    monkeypatch.setattr("chispa.config.FRONT_WINDOWS_H", {12: (6, 18), 24: (6, 30)})
    monkeypatch.setattr("chispa.config.FRONT_REACH_M", {12: 5000.0, 24: 8000.0})
    monkeypatch.setattr("chispa.config.FRONT_MASK_HOURS", 2)
    monkeypatch.setattr("chispa.config.FRONT_HIDDEN_SHARE", 0.5)
    monkeypatch.setattr("chispa.config.GROWTH_FLOOR_M", 850.0)
    monkeypatch.setattr("chispa.config.FRONT_DAY_HOURS_UTC", (14, 21))


def pixels_of(later: list[tuple[float, float]]) -> dict:
    """A front of three pixels in a row to the east at 05:00. Later pixels: (hours, metres east)."""
    seconds = np.array([START, START, START] + [START + hours * HOUR for hours, _ in later])
    east = np.array([0.0, 400.0, 800.0] + [metres for _, metres in later])
    lat, lon = np.full(len(east), LAT), LON + east * EAST
    found = {"seconds": seconds, "lat": lat, "lon": lon, "points": fronts.metres(lat, lon)}
    # A pixel is available 3 hours after its pass.
    return found | {"look": fronts.looks(seconds), "available": seconds + 3 * HOUR}


def masks_of(first_day: dict[int, int], second_day: dict[int, int]) -> steps.Masks:
    """One GOES pixel at the front. Each day has {hour of the scan: kind of the pixel}."""
    tree = cKDTree(fronts.metres(np.array([LAT]), np.array([LON + 400 * EAST])))
    days = {}
    for day, scans in ((date(2023, 9, 1), first_day), (date(2023, 9, 2), second_day)):
        midnight = datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp()
        times = np.array([midnight + hour * HOUR for hour in scans])
        days[day] = (times, np.array([[kind] for kind in scans.values()], dtype=np.uint8))
    return steps.Masks(None, tree, days)


def rows_of(pixels: dict, masks: steps.Masks) -> dict:
    a, b, look = next(fronts.each_look(pixels))
    return steps.look_rows(pixels, (a, b), look, masks)


def answers_of(pixels: dict, masks: steps.Masks) -> tuple[int, int]:
    rows = rows_of(pixels, masks)
    return int(rows["answer_12"][0]), int(rows["answer_24"][0])


def test_no_pixel_and_cloud_is_not_visible():
    masks = masks_of({17: CLOUD}, {5: SEEN})
    assert answers_of(pixels_of([]), masks) == (steps.HIDDEN, steps.HIDDEN)


def test_no_pixel_and_a_clear_view_is_clear_with_no_fire():
    masks = masks_of({17: SEEN}, {5: SEEN})
    assert answers_of(pixels_of([]), masks) == (2, 2)


def test_the_block_out_zone_gives_the_scan_before_it():
    # The scan of 17:00 is nearest to 12 hours after the look, but it is in the block-out zone.
    masks = masks_of({16: SEEN, 17: BLOCKED}, {5: SEEN})
    assert answers_of(pixels_of([]), masks) == (2, 2)


def test_a_scan_farther_than_the_limit_gives_no_answer():
    masks = masks_of({13: SEEN}, {5: SEEN})
    assert answers_of(pixels_of([]), masks) == (steps.HIDDEN, steps.HIDDEN)


def test_a_pixel_on_the_front_is_the_front_again_and_a_far_pixel_is_new_ground():
    # 12 hours later: one pixel 300 m from the front. 24 hours later: one pixel 1200 m past it.
    pixels = pixels_of([(12, 500.0), (24, 2000.0)])
    assert answers_of(pixels, masks_of({17: CLOUD}, {5: CLOUD})) == (1, 0)


def test_the_front_again_at_12_hours_and_cloud_at_24_hours_is_not_visible_for_24_hours():
    pixels = pixels_of([(12, 500.0)])
    assert answers_of(pixels, masks_of({17: SEEN}, {5: CLOUD})) == (1, steps.HIDDEN)


def test_examined_says_only_what_goes_saw_and_not_what_viirs_found():
    # New ground at 24 hours under cloud: the front has an answer, and GOES did not examine it.
    rows = rows_of(pixels_of([(12, 500.0), (24, 2000.0)]), masks_of({17: SEEN}, {5: CLOUD}))
    assert (int(rows["answer_12"][0]), int(rows["answer_24"][0])) == (1, 0)
    assert (bool(rows["examined_12"][0]), bool(rows["examined_24"][0])) == (True, False)
    # The look is complete when its pixels are available: 3 hours after its pass.
    assert rows["complete_h"][0] == 3.0


def test_the_table_counts_the_answers_of_the_day_looks_and_the_night_looks():
    night, day = START, START + 12 * HOUR  # 05:00 and 17:00 UTC.
    rows = {
        "start": np.array([night, night, day, day]),
        "answer_12": np.array([0, 2, steps.HIDDEN, 1]),
        "answer_24": np.array([0, 0, 1, 1]),
        "new_12": np.array([12, 0, 0, 0]),
        "new_24": np.array([12, 3, 0, 0]),
        "examined_12": np.array([True, True, False, True]),
        "examined_24": np.array([True, False, False, False]),
        "complete_h": np.array([4.0, 4.0, 5.0, 5.0]),
        "distance_m_12": np.array([1500.0, np.nan, np.nan, np.nan]),
        "distance_m_24": np.array([1500.0, 2500.0, np.nan, np.nan]),
    }
    table = {(row["hours"], row["looks"]): row for row in steps.step_table(rows)}
    assert table[(12, "night")]["new_ground"] == 1 and table[(12, "night")]["clear_no_fire"] == 1
    assert table[(12, "day")]["not_visible"] == 1 and table[(12, "day")]["front_again"] == 1
    # One front of the three that were visible has new ground.
    assert table[(12, "all")]["new_ground_share"] == round(1 / 3, 4)
    assert table[(12, "all")]["fronts_with_10_new_pixels"] == 1
    assert table[(24, "all")]["distance_m_median"] == 2000.0
    # At 24 hours, GOES did not examine the front 2 (new ground) and the fronts 3 and 4 (again).
    assert table[(24, "all")]["new_ground_not_examined"] == 1
    assert table[(24, "all")]["front_again_not_examined"] == 2
    assert table[(12, "all")]["new_ground_not_examined"] == 0
    assert table[(12, "night")]["look_complete_h_median"] == 4.0


def test_a_front_of_a_look_after_the_end_of_the_test_year_does_not_count(monkeypatch):
    monkeypatch.setattr("chispa.config.FRONT_MIN_PIXELS", 3)
    monkeypatch.setattr("chispa.config.FRONT_TEST_END", datetime(2023, 9, 1, 12, tzinfo=UTC))
    grid = pantanal_grid()
    rows = {
        "pixels": np.array([3, 3, 2]),
        "lat": np.full(3, LAT),
        "lon": np.full(3, LON),
        "start": np.array([START, START + 12 * HOUR, START]),  # 05:00, 17:00 and 05:00 UTC.
        "complete_h": np.full(3, 4.0),
    }
    in_biome = np.ones((grid.height, grid.width), dtype=bool)
    assert steps.kept(rows, in_biome).tolist() == [True, False, False]


def rows_at(start: datetime, complete_h: float) -> dict:
    rows = {"pixels": np.array([3]), "lat": np.array([LAT]), "lon": np.array([LON])}
    return rows | {"start": np.array([start.timestamp()]), "complete_h": np.array([complete_h])}


def test_a_front_needs_its_longest_window_in_the_year_and_a_complete_look(monkeypatch):
    monkeypatch.setattr("chispa.config.FRONT_MIN_PIXELS", 3)
    monkeypatch.setattr("chispa.config.FRONT_TEST_END", datetime(2026, 11, 21, tzinfo=UTC))
    grid = pantanal_grid()
    in_biome = np.ones((grid.height, grid.width), dtype=bool)
    # 30 December 2023 at 17:00: the window of 24 hours ends at 23:00 on 31 December.
    assert steps.kept(rows_at(datetime(2023, 12, 30, 17, tzinfo=UTC), 4.0), in_biome).tolist() == [
        True
    ]
    # 31 December at 05:00: the window ends in January, and the pixels of January are not there.
    assert steps.kept(rows_at(datetime(2023, 12, 31, 5, tzinfo=UTC), 4.0), in_biome).tolist() == [
        False
    ]
    # A look that was complete 7 hours after its start: the first window started at 6 hours.
    assert steps.kept(rows_at(datetime(2023, 9, 1, 5, tzinfo=UTC), 7.0), in_biome).tolist() == [
        False
    ]
