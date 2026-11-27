"""Tests of the Open-Meteo source against a small real answer: two cells, two days of 2026."""

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import requests

from chispa.sources import openmeteo, weather

SAMPLE = Path(__file__).parent / "samples" / "openmeteo" / "two_cells.json"
PREVIOUS = SAMPLE.parent / "previous_two_cells.json"


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


def test_a_forecast_of_the_past_keeps_an_hour_with_no_value_as_no_value(tmp_path):
    found = json.loads(PREVIOUS.read_text())
    # The humidity of hour 5 of the first day of the first cell is absent, as in April 2026.
    found[0]["hourly"]["dew_point_2m_previous_day1"][5] = None
    (tmp_path / "answer.json").write_text(json.dumps(found))
    days, wind = openmeteo.read(tmp_path / "answer.json", lead=1)
    whole, _ = openmeteo.read(PREVIOUS, lead=1)
    # Only the dryness of that day of that cell has no value. Each other value stays.
    assert np.isnan(days["vpd_kpa"][0, 0]) and not np.isnan(wind).any()
    days["vpd_kpa"][0, 0] = whole["vpd_kpa"][0, 0]
    assert all(np.array_equal(days[name], whole[name]) for name in weather.MEASURES)


class Answers:
    """A stand-in for `requests.get`: no answer comes for the first requests, then one comes."""

    def __init__(self, with_no_answer: int, error: type = requests.exceptions.ReadTimeout):
        self.with_no_answer, self.error, self.requests = with_no_answer, error, 0

    def __call__(self, url: str, params: dict, timeout: float):
        self.requests += 1
        if self.requests <= self.with_no_answer:
            raise self.error
        return SimpleNamespace(status_code=200, text="[]")


@pytest.mark.parametrize("error", [requests.exceptions.ReadTimeout, requests.ConnectionError])
def test_a_request_with_no_answer_is_sent_again(tmp_path, monkeypatch, error):
    monkeypatch.setattr("chispa.config.OPENMETEO_TRIES", 3)
    monkeypatch.setattr("chispa.config.OPENMETEO_PAUSE_S", 0)
    get = Answers(with_no_answer=2, error=error)
    monkeypatch.setattr(requests, "get", get)
    days = (date(2025, 9, 1), date(2025, 9, 3))
    openmeteo.download_previous(np.array([-18.0]), np.array([-57.0]), days, tmp_path / "a.json")
    assert (get.requests, (tmp_path / "a.json").read_text()) == (3, "[]")


def test_the_last_request_with_no_answer_stops_the_run(tmp_path, monkeypatch):
    monkeypatch.setattr("chispa.config.OPENMETEO_TRIES", 3)
    monkeypatch.setattr("chispa.config.OPENMETEO_PAUSE_S", 0)
    get = Answers(with_no_answer=3)
    monkeypatch.setattr(requests, "get", get)
    days = (date(2025, 9, 1), date(2025, 9, 3))
    with pytest.raises(requests.exceptions.ReadTimeout):
        openmeteo.download_previous(np.array([-18.0]), np.array([-57.0]), days, tmp_path / "a.json")
    assert get.requests == 3 and not (tmp_path / "a.json").exists()
