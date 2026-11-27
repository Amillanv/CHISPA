"""Tests of the live growth forecast, with cases small enough for paper."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from chispa import checks, fronts
from chispa.evaluation import forecast_live, forecast_trees
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
    assert second["no_forecast"] == forecast_live.NO_INPUTS and second["pixels"] == 4
    # The window keeps its limits, thus a reader knows when it ends.
    nothing = {"new_ground": None, "large_growth": None, "sectors": None}
    assert second["hours_24"] == {"from": "a", "to": "c"} | nothing


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
        return forecast_trees.mark(tmp_path / "store.sqlite")

    first = add(1, "2023-09-01T05:00:00+00:00")
    assert forecast_trees.mark(tmp_path / "store.sqlite") == first
    # A detection of a year that the trees do not learn from changes nothing.
    assert add(2, "2026-11-25T17:00:00+00:00") == first
    # One more detection of a development year: the saved trees are not those of this store.
    second = add(3, "2023-09-01T17:00:00+00:00")
    assert second != first
    # Two fire powers change, and their number and their sum stay: the mark changes also.
    store.execute("UPDATE detections SET frp_mw = 9.0 WHERE id = 1")
    store.execute("UPDATE detections SET frp_mw = 1.0 WHERE id = 3")
    store.commit()
    assert forecast_trees.mark(tmp_path / "store.sqlite") != second


def test_saved_trees_with_other_inputs_stop_the_forecast(monkeypatch):
    places = {"lat": np.array([-16.82]), "lon": np.array([-55.02]), "pixels": np.array([9])}
    saved = {"models": {("new_ground", 12): Fixed(0.1)}, "names": {("new_ground", 12): ("old",)}}
    inputs = {"log_pixels": np.array([2.3]), "past_vpd": np.array([2.0])}
    inputs["log_frp_mean"] = np.array([1.0])
    with pytest.raises(RuntimeError, match="its inputs are not the inputs of now"):
        forecast_live.front_rows(saved, places, inputs, {12: {}})


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
    # One look with two fronts 20 km apart. The pixels of the first front came in the alerts 7
    # and 8, which merged into the event 7. Those of the second came in the alert 9. The second
    # front is too small to count.
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
        merged = 7 if event == 8 else event
        store.execute("INSERT INTO memberships VALUES (?, ?, 'LOW', ?)", (number, merged, event))
    look = fronts.make_look(pixels["points"], pixels["points"][:0])
    one = {"bounds": (0, 5), "look": look, "keep": np.bincount(look.labels) >= 3}
    assert forecast_live.front_events(store, pixels, one) == [[7, 8]]


def test_the_live_forecast_has_only_the_pixels_that_were_available(tmp_path):
    # Two pixels of one pass at 05:00. The first was available at 08:00, the second at 11:00.
    store = open_store(tmp_path / "store.sqlite")
    when = to_text(datetime.fromtimestamp(START, UTC))
    for number, hours in enumerate((3, 6), start=1):
        had = to_text(datetime.fromtimestamp(START + hours * HOUR, UTC))
        place = (LAT, LON + number * 400 * EAST)
        row = (number, "firms", "viirs", "NOAA20", when, had, *place, 375.0, 5.0, "nominal", 1)
        store.execute("INSERT INTO detections VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", row)
    at = datetime.fromtimestamp(START, UTC)
    assert len(forecast_live.pixels_at(store, 2023, at + timedelta(hours=4))["seconds"]) == 1
    assert len(forecast_live.pixels_at(store, 2023, at + timedelta(hours=7))["seconds"]) == 2
    # Before the first pixel was available, we had no pixel of the year.
    assert forecast_live.pixels_at(store, 2023, at + timedelta(hours=1)) is None
    assert forecast_live.pixels_at(store, 2024, at + timedelta(hours=7)) is None


def test_the_step_of_the_update_says_why_it_made_no_forecast(monkeypatch, capsys):
    now = datetime(2027, 1, 2, tzinfo=UTC)

    def no_map(*arguments):
        raise RuntimeError("Run `chispa fetch burned --year 2026` first.")

    # A layer is absent: the update does not stop, and the text says what to do.
    monkeypatch.setattr(forecast_live, "live_looks", no_map)
    checks.run_new_forecasts(now)
    assert capsys.readouterr().out == (
        "forecast: no forecast. Run `chispa fetch burned --year 2026` first.\n"
    )
    # The saved trees are not those of now: the step fits no trees, and it says so.
    monkeypatch.setattr(forecast_live, "live_looks", lambda *arguments: None)
    checks.run_new_forecasts(now)
    assert "the saved trees are not those of now" in capsys.readouterr().out


def test_the_next_update_makes_the_forecast_that_the_weather_stopped(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("chispa.config.FORECAST_LIVE_DIR", tmp_path)
    front = {"lat": LAT, "lon": LON, "pixels": 4, "events": [7]}
    look = {"look_at": "2026-11-25T17:19+00:00", "large_growth_pixels": 10, "fronts": [front]}
    answers = [OSError("Open-Meteo gave no answer."), [look]]

    def live(*arguments):
        found = answers.pop(0)
        if isinstance(found, OSError):
            raise found
        return found

    monkeypatch.setattr(forecast_live, "live_looks", live)
    # The weather does not come in the first update. The second update has no new detection.
    checks.run_new_forecasts(datetime(2026, 11, 25, 21, 0, tzinfo=UTC))
    assert capsys.readouterr().out == "forecast: no forecast. Open-Meteo gave no answer.\n"
    assert list(tmp_path.iterdir()) == []
    checks.run_new_forecasts(datetime(2026, 11, 25, 21, 5, tzinfo=UTC))
    assert capsys.readouterr().out == "forecast: 1 new files.\n"
    assert len(list(tmp_path.glob("2026-11-25T1719_*.json"))) == 1


def test_on_1_january_the_live_forecast_has_the_looks_of_31_december(tmp_path, monkeypatch):
    monkeypatch.setattr("chispa.config.FORECAST_LIVE_HOURS", 24)
    grid = pantanal_grid()
    in_biome = np.ones((grid.height, grid.width), dtype=bool)
    monkeypatch.setattr(forecast_live, "_biome", lambda raw_dir: in_biome)
    store = open_store(tmp_path / "store.sqlite")
    insert = "INSERT INTO detections VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    # Three pixels of one front at 17:00 on 31 December 2026, available 3 hours later.
    times = ("2026-12-31T17:00:00+00:00", "2026-12-31T20:00:00+00:00")
    for number in (1, 2, 3):
        place = (LAT, LON + number * 400 * EAST)
        row = (number, "firms", "viirs", "NOAA20", *times, *place, 375.0, 5.0, "nominal", 1)
        store.execute(insert, row)
    # At 02:00 on 1 January the new year has no pixel, and the look of 31 December is 9 hours old.
    found = forecast_live.recent_looks(store, tmp_path, datetime(2027, 1, 1, 2, tzinfo=UTC))
    assert [one["places"]["pixels"].tolist() for _, one in found] == [[3]]
    # A front of four pixels of the new year comes at 05:00. The two looks are in the last 24 hours.
    times = ("2027-01-01T05:00:00+00:00", "2027-01-01T07:00:00+00:00")
    for number in (4, 5, 6, 7):
        place = (LAT, LON + number * 400 * EAST)
        row = (number, "firms", "viirs", "NOAA20", *times, *place, 375.0, 5.0, "nominal", 1)
        store.execute(insert, row)
    found = forecast_live.recent_looks(store, tmp_path, datetime(2027, 1, 1, 8, tzinfo=UTC))
    assert [one["places"]["pixels"].tolist() for _, one in found] == [[3], [4]]
    # At 18:00 the look of 31 December is older than 24 hours.
    found = forecast_live.recent_looks(store, tmp_path, datetime(2027, 1, 1, 18, tzinfo=UTC))
    assert [one["places"]["pixels"].tolist() for _, one in found] == [[4]]
