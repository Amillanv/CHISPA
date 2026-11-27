"""Tests of the live growth forecast, with cases small enough for paper."""

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from chispa import fronts
from chispa.evaluation import forecast_live
from chispa.evaluation.front_inputs import Layers
from chispa.grid import pantanal_grid
from chispa.store import open_store, to_text

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


class Fixed:
    """A model that gives the same chance for each row."""

    def __init__(self, chance: float) -> None:
        self.chance = chance

    def predict_proba(self, table: np.ndarray) -> np.ndarray:
        return np.column_stack(
            [np.full(len(table), 1 - self.chance), np.full(len(table), self.chance)]
        )


def look_of(pixels: int, made_at: str) -> dict:
    """The forecast of a look with one front, seen at 16:34 UTC on 22 November 2026."""
    front = {"lat": -16.82, "lon": -55.02, "pixels": pixels}
    return {"look_at": "2026-11-22T16:34+00:00", "made_at": made_at, "fronts": [front]}


def two_fronts(power: list[float]) -> tuple[dict, dict, dict]:
    """Two fronts with their inputs, and saved models that give a fixed chance for each question."""
    places = {"lat": np.array([-16.82, -17.35]), "lon": np.array([-55.02, -57.24])}
    places["pixels"] = np.array([9, 4])
    inputs = {"log_pixels": np.log1p(places["pixels"]), "past_vpd": np.array([2.0, 2.0])}
    inputs |= {"log_frp_mean": np.array(power), "reach_km_s": np.zeros((2, 8))}
    chances = {"new_ground": 0.13, "large_growth": 0.03, "sector": 0.05}
    keys = [(question, hours) for question in chances for hours in (12, 24)]
    saved = {"models": {key: Fixed(chances[key[0]]) for key in keys}, "names": {}}
    front = ("log_pixels", "past_vpd", "log_frp_mean")
    for key in keys:
        saved["names"][key] = (*front, "reach_km_s") if key[0] == "sector" else front
    return saved, places, inputs


def test_a_front_has_its_place_and_the_chances_of_each_window(monkeypatch):
    monkeypatch.setattr("chispa.config.FRONT_SECTORS", 8)
    windows = {12: {"from": "a", "to": "b"}, 24: {"from": "a", "to": "c"}}
    first, second = forecast_live.front_rows(*two_fronts([1.0, 1.0]), windows)
    assert (first["lat"], first["lon"], first["pixels"]) == (-16.82, -55.02, 9)
    assert second["pixels"] == 4 and set(first) == {"lat", "lon", "pixels", "hours_12", "hours_24"}
    assert first["hours_24"]["new_ground"] == 0.13 and first["hours_24"]["large_growth"] == 0.03
    assert first["hours_12"]["sectors"] == dict.fromkeys(forecast_live.SECTORS, 0.05)
    assert (first["hours_12"]["to"], first["hours_24"]["to"]) == ("b", "c")


def test_a_front_with_no_fire_power_gets_no_chance(monkeypatch):
    monkeypatch.setattr("chispa.config.FRONT_SECTORS", 8)
    # The trees did not learn from a front with no fire power, and they have no score for it.
    windows = {24: {"from": "a", "to": "c"}}
    first, second = forecast_live.front_rows(*two_fronts([1.0, np.nan]), windows)
    assert first["hours_24"]["new_ground"] == 0.13 and "no_forecast" not in first
    assert second["hours_24"] is None and second["no_forecast"] == forecast_live.NO_INPUTS
    assert second["pixels"] == 4


def test_a_window_that_ended_gets_no_forecast():
    look_at = datetime(2026, 11, 25, 17, 0, tzinfo=UTC)
    # 5 hours after the look: the two windows are open. The 12 hours window is 6 to 18 hours.
    early = forecast_live.open_windows(look_at, look_at + timedelta(hours=5))
    assert early[12] == {"from": "2026-11-25T23:00+00:00", "to": "2026-11-26T11:00+00:00"}
    assert early[24] == {"from": "2026-11-25T23:00+00:00", "to": "2026-11-26T23:00+00:00"}
    # 10 hours after the look, the window of 12 hours is in progress: it stays, with its limits.
    assert set(forecast_live.open_windows(look_at, look_at + timedelta(hours=10))) == {12, 24}
    # 18 hours after the look, the window of 12 hours ended.
    assert set(forecast_live.open_windows(look_at, look_at + timedelta(hours=18))) == {24}


def test_the_mark_of_the_saved_trees_changes_with_a_training_detection(tmp_path, monkeypatch):
    monkeypatch.setattr("chispa.config.FRONT_YEARS", (2023,))
    store = open_store(tmp_path / "store.sqlite")
    insert = "INSERT INTO detections VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"

    def add(number: int, when: str) -> str:
        row = (number, "firms", "viirs", "NOAA20", when, when, LAT, LON, 375.0, 5.0, "nominal", 1)
        store.execute(insert, row)
        store.commit()
        return forecast_live._stamp(tmp_path / "store.sqlite")

    first = add(1, "2023-09-01T05:00:00+00:00")
    assert forecast_live._stamp(tmp_path / "store.sqlite") == first
    # A detection of a year that the trees do not learn from changes nothing.
    assert add(2, "2026-11-25T17:00:00+00:00") == first
    # One more detection of a development year: the saved trees are not those of this store.
    second = add(3, "2023-09-01T17:00:00+00:00")
    assert second != first
    # Two fire powers change, and their number and their sum stay: the mark changes also.
    store.execute("UPDATE detections SET frp_mw = 9.0 WHERE id = 1")
    store.execute("UPDATE detections SET frp_mw = 1.0 WHERE id = 3")
    store.commit()
    assert forecast_live._stamp(tmp_path / "store.sqlite") != second


def test_saved_trees_with_other_inputs_stop_the_forecast(monkeypatch):
    places = {"lat": np.array([-16.82]), "lon": np.array([-55.02]), "pixels": np.array([9])}
    saved = {"models": {("new_ground", 12): Fixed(0.1)}, "names": {("new_ground", 12): ("old",)}}
    inputs = {"log_pixels": np.array([2.3]), "past_vpd": np.array([2.0])}
    inputs["log_frp_mean"] = np.array([1.0])
    with pytest.raises(RuntimeError, match="its inputs are not the inputs of now"):
        forecast_live.front_rows(saved, places, inputs, {12: {}})


def test_the_first_forecast_of_a_look_stays_when_a_newer_one_comes(tmp_path):
    first = forecast_live.save([look_of(9, "2026-11-22T20:00+00:00")], tmp_path)
    assert [path.name for path in first] == ["2026-11-22T1634_2026-11-22T2000.json"]
    # The same look again with the same pixels: no new file.
    assert forecast_live.save([look_of(9, "2026-11-22T20:05+00:00")], tmp_path) == []
    # A second satellite gave more pixels: a new file, and the first file stays as it was.
    second = forecast_live.save([look_of(12, "2026-11-22T21:00+00:00")], tmp_path)
    assert [path.name for path in second] == ["2026-11-22T1634_2026-11-22T2100.json"]
    assert json.loads(first[0].read_text())["fronts"][0]["pixels"] == 9
    assert forecast_live.save([look_of(12, "2026-11-22T21:05+00:00")], tmp_path) == []


def test_only_the_looks_from_the_start_time_give_fronts():
    # Two looks 12 hours apart. Each has a front of three pixels in a row to the east.
    seconds = np.array([START] * 3 + [START + 12 * HOUR] * 3)
    lon = LON + np.tile([0.0, 400.0, 800.0], 2) * EAST
    lat = np.full(6, LAT)
    pixels = {"seconds": seconds, "lat": lat, "lon": lon, "points": fronts.metres(lat, lon)}
    pixels |= {"look": fronts.looks(seconds), "available": seconds + 3 * HOUR}
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


def test_a_front_lists_the_events_of_its_pixels(tmp_path):
    # One look with two fronts 20 km apart. The pixels of the first front are in the events 7 and
    # 8, and those of the second in the event 9. The second front is too small to count.
    east = np.array([0.0, 400.0, 800.0, 20_000.0, 20_400.0])
    lat, lon = np.full(5, LAT), LON + east * EAST
    seconds = np.full(5, START)
    pixels = {"seconds": seconds, "lat": lat, "lon": lon, "points": fronts.metres(lat, lon)}
    store = open_store(tmp_path / "store.sqlite")
    when = to_text(datetime.fromtimestamp(START, UTC))
    for number, event in enumerate((7, 7, 8, 9, 9), start=1):
        place = (float(lat[number - 1]), float(lon[number - 1]))
        row = (number, "firms", "viirs", "NOAA20", when, when, *place, 375.0, 5.0, "nominal", 1)
        store.execute("INSERT INTO detections VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", row)
        store.execute("INSERT INTO memberships VALUES (?, ?, 'LOW', ?)", (number, event, event))
    look = fronts.make_look(pixels["points"], pixels["points"][:0])
    one = {"bounds": (0, 5), "look": look, "keep": np.bincount(look.labels) >= 3}
    assert forecast_live.front_events(store, pixels, one) == [[7, 8]]
