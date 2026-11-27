"""Tests of the weather source against a small real file: four cells of two months of 2018."""

from datetime import date
from pathlib import Path

import numpy as np
import pytest

from chispa.sources import weather

SAMPLES = Path(__file__).parent / "samples"


def test_grid_has_a_cell_centre_at_each_tenth_of_a_degree(monkeypatch):
    monkeypatch.setattr("chispa.config.PANTANAL_BOX", (-59.5, -22.5, -54.5, -15.5))
    monkeypatch.setattr("chispa.config.WEATHER_PIXEL_DEG", 0.1)
    grid = weather.weather_grid()
    assert (grid.width, grid.height) == (51, 71)
    assert (round(float(grid.lons()[0]), 6), round(float(grid.lats()[0]), 6)) == (-59.5, -15.5)
    assert (round(float(grid.lons()[-1]), 6), round(float(grid.lats()[-1]), 6)) == (-54.5, -22.5)
    assert grid.rows_cols(np.array([-18.0]), np.array([-57.0])) == (np.array([25]), np.array([25]))


def test_days_of_two_months_are_one_series():
    days = weather.read_days(SAMPLES, date(2018, 1, 31), date(2018, 2, 2))
    assert set(days) == set(weather.MEASURES)
    assert days["rain_mm"].shape == (3, 2, 2)
    # 31 January, 1 February and 2 February at the first cell, as the product gave them.
    assert [round(float(value), 3) for value in days["rain_mm"][:, 0, 0]] == [7.173, 12.453, 12.382]
    first = weather.read_days(SAMPLES, date(2018, 1, 1), date(2018, 1, 3))
    assert [round(float(value), 3) for value in first["wind_kmh"][:, 0, 0]] == [
        11.098,
        11.176,
        5.078,
    ]
    assert round(float(first["temp_c"][0, 0, 0]), 3) == 30.891


def test_month_with_no_file_says_what_to_do():
    with pytest.raises(RuntimeError, match="chispa fetch weather --year 2018"):
        weather.read_days(SAMPLES, date(2018, 2, 20), date(2018, 3, 2))


def test_the_newest_weather_has_each_complete_month_in_sequence():
    days, wind = weather.read_newest(SAMPLES, date(2018, 1, 1), date(2019, 1, 31))
    # January and February 2018 are on disk: 59 days, with four blocks of wind for each day.
    assert days["rain_mm"].shape == (59, 2, 2) and wind.shape == (236, 3, 2, 2)
    # The first block of 31 January and of 1 February at the first cell, as the product gave them:
    # to the east, to the north and the mean speed, in km/h.
    assert [round(float(value), 3) for value in wind[120, :, 0, 0]] == [-0.769, -4.188, 4.377]
    assert [round(float(value), 3) for value in wind[124, :, 0, 0]] == [-1.792, -2.557, 3.165]
    assert [round(float(value), 3) for value in days["rain_mm"][30:33, 0, 0]] == [
        7.173,
        12.453,
        12.382,
    ]


def test_the_newest_weather_stops_at_the_limit_month():
    days, wind = weather.read_newest(SAMPLES, date(2018, 1, 1), date(2018, 1, 31))
    assert days["rain_mm"].shape == (31, 2, 2) and wind.shape == (124, 3, 2, 2)


def test_no_weather_file_from_the_first_month_says_what_to_do():
    with pytest.raises(RuntimeError, match="chispa fetch weather --year 2019"):
        weather.read_newest(SAMPLES, date(2019, 1, 1), date(2019, 1, 31))


def save_part(folder, kind: str, month: str, days: int) -> None:
    """Save the first days of a real month file as a month in progress."""
    saved = np.load(SAMPLES / kind / "2018" / f"{month}.npz")
    count = days if kind == "weather" else days * 24 // weather.BLOCK_HOURS
    (folder / kind / "2018").mkdir(parents=True, exist_ok=True)
    with (folder / kind / "2018" / f"{month}.npz.part").open("wb") as file:
        np.savez_compressed(file, **{name: saved[name][:count] for name in saved.files})


def test_the_first_month_can_be_the_month_in_progress(tmp_path):
    # In the first days of a year, December is not complete: 3 days of it are on disk.
    for kind in ("weather", "wind"):
        save_part(tmp_path, kind, "01", 3)
    days, wind = weather.read_newest(tmp_path, date(2018, 1, 1), date(2019, 1, 31))
    assert days["rain_mm"].shape == (3, 2, 2) and wind.shape == (12, 3, 2, 2)
    assert round(float(days["wind_kmh"][0, 0, 0]), 3) == 11.098


def test_month_in_progress_gives_its_complete_days(tmp_path):
    # The first three days of the real file of February 2018, saved as a month in progress.
    for kind in ("weather", "wind"):
        save_part(tmp_path, kind, "02", 3)
    days, wind = weather.read_part(tmp_path, date(2018, 2, 1))
    assert days["rain_mm"].shape == (3, 2, 2) and wind.shape[:2] == (12, 3)
    # 1 and 2 February at the first cell, as the product gave them.
    assert [round(float(value), 3) for value in days["rain_mm"][:2, 0, 0]] == [12.453, 12.382]


def test_month_with_no_file_in_progress_gives_none(tmp_path):
    assert weather.read_part(tmp_path, date(2018, 2, 1)) is None
