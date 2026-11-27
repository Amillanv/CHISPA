"""Tests of the weather forecast of a look, against a small real answer of Open-Meteo.

The answer has two cells of the forecast model for 18 to 20 November 2026: the values that the
model predicted 1 day and 2 days before each hour.
"""

from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pytest

from chispa.evaluation import forecast_weather
from chispa.evaluation.front_inputs import Layers
from chispa.sources import openmeteo, weather

SAMPLE = Path(__file__).parent / "samples" / "openmeteo" / "previous_two_cells.json"


@pytest.fixture(autouse=True)
def fixed_values(monkeypatch):
    monkeypatch.setattr("chispa.config.FORECAST_WEATHER_DEG", 0.25)
    monkeypatch.setattr("chispa.config.PANTANAL_BOX", (-59.5, -22.5, -54.5, -15.5))
    monkeypatch.setattr("chispa.config.WEATHER_PIXEL_DEG", 0.1)


def test_a_position_gets_the_cell_of_the_forecast_model():
    cells = forecast_weather.cells_of(np.array([-18.04, -19.4]), np.array([-57.1, -56.62]))
    assert cells.tolist() == [[-18.0, -57.0], [-19.5, -56.5]]


def test_the_forecast_of_each_lead_is_not_the_same():
    days_1, wind_1 = openmeteo.read(SAMPLE, 1)
    days_2, _ = openmeteo.read(SAMPLE, 2)
    assert days_1["rain_mm"].shape == (2, 3) and wind_1.shape == (2, 12, 3)
    # The first cell on 18 November, as the product gave it: the rain that the model predicted
    # 1 day before and 2 days before, and the largest temperature of each day, 1 day before.
    assert round(float(days_1["rain_mm"][0, 0]), 1) == 1.2
    assert round(float(days_2["rain_mm"][0, 0]), 1) == 2.4
    assert [round(float(value), 1) for value in days_1["temp_c"][0]] == [34.3, 33.3, 34.2]


def test_a_front_gets_the_forecast_at_its_weather_cell_for_three_days(tmp_path, monkeypatch):
    grid = weather.weather_grid()
    shape = (20, grid.height, grid.width)
    days = {name: np.zeros(shape, dtype=np.float32) for name in weather.MEASURES}
    layers = Layers(None, (None, None), date(2026, 11, 1), days, np.zeros((80, 3, *shape[1:])))
    # One front near the first cell of the answer, with a look at 05:00 on 18 November.
    start = datetime(2026, 11, 18, 5, 0, tzinfo=UTC).timestamp()
    answers = {"lat": np.array([-18.04]), "lon": np.array([-57.02]), "start": np.array([start])}
    # No request: the saved answer is the file of that day. Its first cell is the cell of the front.
    monkeypatch.setattr(forecast_weather, "day_file", lambda raw_dir, day, asked: SAMPLE)
    found = forecast_weather.forecast_layers(layers, answers, tmp_path)
    row, col = (int(value[0]) for value in grid.rows_cols(answers["lat"], answers["lon"]))
    first, second = found[1], found[2]
    # 18 November is day 17 from 1 November. The layers are 3 days longer than the weather.
    assert first.days["rain_mm"].shape[0] == 23 and first.wind.shape[0] == 92
    assert round(float(first.days["rain_mm"][17, row, col]), 1) == 1.2
    assert round(float(second.days["rain_mm"][17, row, col]), 1) == 2.4
    assert np.isnan(first.days["rain_mm"][16, row, col]) and np.isnan(
        first.days["rain_mm"][17, 0, 0]
    )
    assert not np.isnan(first.wind[17 * 4 : 20 * 4, :, row, col]).any()
    assert second.wind.shape == (0,)
