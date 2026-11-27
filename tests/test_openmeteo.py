"""Tests of the Open-Meteo source against a small real answer: two cells, two days of 2026."""

import json
from pathlib import Path

import pytest

from chispa.sources import openmeteo, weather

SAMPLE = Path(__file__).parent / "samples" / "openmeteo" / "two_cells.json"


def test_an_answer_gives_the_measures_of_each_day_and_the_wind_of_each_block():
    days, wind = openmeteo.read(SAMPLE)
    assert set(days) == set(weather.MEASURES)
    assert days["rain_mm"].shape == (2, 2)
    assert wind.shape == (2, 8, len(weather.WIND))
    # The first cell on the two days, as the product gave it.
    assert [round(float(value), 1) for value in days["wind_kmh"][0]] == [20.0, 18.4]
    assert [round(float(value), 1) for value in days["rain_mm"][0]] == [7.5, 1.3]
    assert [round(float(value), 1) for value in days["temp_c"][0]] == [31.8, 34.7]


def test_a_wind_from_the_north_gives_air_that_goes_to_the_south():
    # The first six hours of the first cell: 17.9, 11.1, 10.7, 13.4, 8.6 and 11.4 km/h, from
    # 338, 12, 33, 15, 359 and 355 degrees. The mean speed is 73.1 / 6.
    _, wind = openmeteo.read(SAMPLE)
    east, north, speed = wind[0, 0]
    assert round(float(speed), 3) == 12.183
    assert north < 0 and abs(east) < abs(north)


def test_a_wrong_unit_stops_the_read(tmp_path):
    found = json.loads(SAMPLE.read_text())
    found[0]["hourly_units"]["wind_speed_10m"] = "mp/h"
    (tmp_path / "answer.json").write_text(json.dumps(found))
    with pytest.raises(ValueError, match="wind_speed_10m has the unit mp/h"):
        openmeteo.read(tmp_path / "answer.json")


def test_an_hour_with_no_value_stops_the_read(tmp_path):
    found = json.loads(SAMPLE.read_text())
    found[1]["hourly"]["precipitation"][5] = None
    (tmp_path / "answer.json").write_text(json.dumps(found))
    with pytest.raises(ValueError, match="precipitation has an hour with no value"):
        openmeteo.read(tmp_path / "answer.json")
