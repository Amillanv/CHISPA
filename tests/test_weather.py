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
