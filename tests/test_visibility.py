"""Tests of the visibility table, with cases small enough for paper."""

import numpy as np

from chispa.evaluation import visibility
from chispa.grid import Grid


def test_main_pixel_is_the_goes_pixel_that_holds_most_of_a_fire():
    grid = Grid(west=0.0, north=4.0, pixel_deg=1.0, width=4, height=4)
    numbers = np.zeros((4, 4), dtype=int)
    numbers[0, 0:3] = 1  # Fire 1: latitude 3.5, longitudes 0.5, 1.5 and 2.5.
    numbers[3, 3] = 2  # Fire 2: latitude 0.5, longitude 3.5.
    # Two GOES pixels in one row: the west pixel at longitude 1, the east pixel at longitude 3.5.
    mask_grid = {"lat": np.array([[2.0, 2.0]]), "lon": np.array([[1.0, 3.5]])}
    pixels = visibility.main_pixels(numbers, grid, np.array([1, 2]), mask_grid)
    assert pixels == {1: (0, 0), 2: (0, 1)}


def test_scans_count_only_in_the_days_when_the_fire_burned(monkeypatch):
    monkeypatch.setattr("chispa.config.EVAL_DAY_MARGIN", 0)
    fires = {
        "first_day": np.array([0, 10]),
        "last_day": np.array([0, 11]),
        "month": np.array([0, 0]),
    }
    times = np.array(["2024-01-09T12", "2024-01-10T00", "2024-01-10T12", "2024-01-11T12"])
    times = times.astype("datetime64[s]")
    classes = np.array([[100], [100], [200], [15]], dtype=np.uint8)  # no fire, cloud, possible
    counts = visibility.fire_rows(fires, np.array([1]), times, classes)
    assert {name: values.tolist() for name, values in counts.items()} == {
        "scans": [3],
        "examined": [2],
        "cloud": [1],
        "possible_fire": [1],
    }


def test_table_gives_the_median_shares_of_each_part():
    counts = {
        "scans": np.array([10, 10, 0, 4]),
        "examined": np.array([10, 2, 0, 0]),
        "cloud": np.array([0, 8, 0, 4]),
        "possible_fire": np.array([0, 1, 0, 0]),
    }
    parts = {"a": np.array([True, True, True, False]), "b": np.array([False, False, False, True])}
    first, second = visibility.table(counts, parts)
    assert (first["count"], first["with_scans"], first["scans_median"]) == (3, 2, 10.0)
    assert (first["examined_share_median"], first["cloud_share_median"]) == (0.6, 0.4)
    assert (first["examined_under_half"], first["never_examined"]) == (1, 0)
    assert first["with_possible_fire"] == 1
    assert (second["never_examined"], second["cloud_share_median"]) == (1, 1.0)


def test_month_table_separates_a_hole_from_a_day_of_cloud(tmp_path):
    folder = tmp_path / "goes_mask" / "2024"
    folder.mkdir(parents=True)
    clear = np.full((2, 2, 2), 100, dtype=np.uint8)  # two scans, each pixel examined
    cloud = np.full((2, 2, 2), 200, dtype=np.uint8)
    cloud[0, 0, 0] = 100  # one of the eight values is examined
    times = np.array(["2024-01-01T00:00:00+00:00", "2024-01-01T01:00:00+00:00"])
    np.savez(folder / "2024-01-01.npz", times=times, mask=clear)
    np.savez(folder / "2024-01-02.npz", times=times, mask=cloud)
    np.savez(
        folder / "2024-01-03.npz", times=np.array([]), mask=np.zeros((0, 2, 2), dtype=np.uint8)
    )
    (row,) = visibility.month_table(2024, tmp_path)
    assert (row["month"], row["days"], row["days_with_no_scan"], row["scans"]) == (
        "2024-01",
        3,
        1,
        4,
    )
    assert (row["examined_share"], row["cloud_share"]) == (0.56, 0.44)
    assert row["days_examined_under_quarter"] == 1
