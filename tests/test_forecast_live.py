"""Tests of the live growth forecast, with cases small enough for paper."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from chispa import fronts
from chispa.evaluation import forecast_live
from chispa.evaluation.front_inputs import Layers
from chispa.grid import pantanal_grid

SAMPLE = Path(__file__).parent / "samples" / "openmeteo" / "two_cells.json"
LAT, LON = -19.0, -57.0
EAST = 1 / (111_320 * np.cos(np.deg2rad(19.0)))  # One metre east in degrees, at the box centre.
START = datetime(2023, 9, 1, 5, 0, tzinfo=UTC).timestamp()
HOUR = 3600.0


@pytest.fixture(autouse=True)
def fixed_values(monkeypatch):
    monkeypatch.setattr("chispa.config.LOOK_GAP", timedelta(hours=3))
    monkeypatch.setattr("chispa.config.FRONT_LINK_M", 1500.0)
    monkeypatch.setattr("chispa.config.FRONT_MIN_PIXELS", 3)
    monkeypatch.setattr("chispa.config.FRONT_REACH_M", {12: 5000.0, 24: 8000.0})
    monkeypatch.setattr("chispa.config.GROWTH_FLOOR_M", 850.0)
    monkeypatch.setattr("chispa.config.FRONT_WINDOWS_H", {12: (6, 18), 24: (6, 30)})
    monkeypatch.setattr("chispa.config.FRONT_LARGE_PIXELS", 10)
    monkeypatch.setattr("chispa.config.DASHBOARD_TIME_ZONE", "America/Campo_Grande")


def row_of(pixels: int) -> dict:
    """The forecast of one front, seen at 16:34 UTC on 22 November 2026."""
    row = {"look_at": "2026-11-22T16:34+00:00", "made_at": "2026-11-22T20:00+00:00"}
    row |= {"lat": -16.82, "lon": -55.02, "pixels": pixels}
    row |= {"new_ground_12": 0.13, "large_growth_12": 0.03}
    row |= {"new_ground_24": 0.34, "large_growth_24": 0.07}
    for hours in (12, 24):
        row |= {f"{name}_{hours}": 0.01 for name in forecast_live.SECTORS}
    row |= {"south_24": 0.2, "west_24": 0.3, "north-east_24": 0.1}
    return row


def test_the_text_has_the_local_time_and_the_most_likely_sectors():
    lines = forecast_live.text(row_of(9)).splitlines()
    # 16:34 UTC is 12:34 in the Pantanal.
    assert lines[0] == "A front of 9 pixels near 16.82 S, 55.02 W, seen at 12:34 on 22 November."
    assert lines[1] == "  New ground in 12 hours: 13%. 10 or more new pixels: 3%."
    assert lines[2] == "  New ground in 24 hours: 34%. 10 or more new pixels: 7%."
    assert lines[3] == "  The most likely sectors in 24 hours: west 30%, south 20%, north-east 10%."


def test_a_look_keeps_its_first_file_until_it_has_more_pixels(tmp_path):
    first = forecast_live.save([row_of(9)], tmp_path)
    assert [path.name for path in first] == ["2026-11-22T1634.csv"]
    # The same look again, with the same pixels: the file stays. With more pixels: a new file.
    assert forecast_live.save([row_of(9) | {"made_at": "later"}], tmp_path) == []
    assert "2026-11-22T20:00+00:00" in first[0].read_text()
    assert forecast_live.save([row_of(12) | {"made_at": "later"}], tmp_path) == first
    assert "later" in first[0].read_text()


def test_only_the_looks_from_the_start_time_give_fronts():
    # Two looks 12 hours apart. Each has a front of three pixels in a row to the east.
    seconds = np.array([START] * 3 + [START + 12 * HOUR] * 3)
    lon = LON + np.tile([0.0, 400.0, 800.0], 2) * EAST
    lat = np.full(6, LAT)
    pixels = {"seconds": seconds, "lat": lat, "lon": lon, "points": fronts.metres(lat, lon)}
    pixels["look"] = fronts.looks(seconds)
    grid = pantanal_grid()
    in_biome = np.ones((grid.height, grid.width), dtype=bool)
    found = forecast_live.newest_fronts(pixels, in_biome, START + HOUR)
    assert [one["bounds"] for one in found] == [(3, 6)]
    assert found[0]["places"]["pixels"].tolist() == [3]
    assert forecast_live.newest_fronts(pixels, in_biome, START + 13 * HOUR) == []
    assert forecast_live.newest_fronts(pixels, np.zeros_like(in_biome), START) == []


def test_the_days_of_open_meteo_come_after_the_last_day_at_their_cells():
    # Three days of layers on a grid of 2 rows and 3 columns. The answer has two cells, two days.
    days = {name: np.zeros((3, 2, 3), dtype=np.float32) for name in forecast_live.weather.MEASURES}
    layers = Layers(None, (None, None), date(2026, 11, 16), days, np.zeros((12, 3, 2, 3)))
    cells = np.array([[0, 1], [1, 2]])
    found = forecast_live.newest_days(layers, cells, SAMPLE)
    assert found.days["rain_mm"].shape == (5, 2, 3) and found.wind.shape == (20, 3, 2, 3)
    # The first cell on 19 and 20 November, as the product gave it. A cell with no answer: no value.
    assert [round(float(value), 1) for value in found.days["wind_kmh"][3:, 0, 1]] == [20.0, 18.4]
    assert [round(float(value), 1) for value in found.days["rain_mm"][3:, 0, 1]] == [7.5, 1.3]
    assert np.isnan(found.days["rain_mm"][3:, 0, 0]).all()
    assert round(float(found.wind[12, 2, 0, 1]), 3) == 12.183
    assert found.days["rain_mm"][:3].sum() == 0
