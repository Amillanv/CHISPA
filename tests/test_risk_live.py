"""Tests of the live growth risk, with cases small enough for paper."""

import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pytest

from chispa import record, risk, risk_files, risk_live, risk_weather
from chispa.fusion import fuse
from chispa.grid import Grid
from chispa.store import add_detections, open_store, read_detections, replace_fusion, to_text
from tests.test_fusion import KM, T0, VIIRS

FIRST_ID = 2024 * 10_000_000
# VIIRS is at lat -17.5, lon -57.5. It was observed at T0 and was available 3 hours later.
FAR = replace(VIIRS, lat=-19.5, platform="NOAA20")
# A detection of 2 days before, 500 m to the north: a different alert, more than the fusion window.
EARLIER = replace(
    VIIRS,
    lat=-17.5 + 0.5 * KM,
    sensor_family="modis",
    platform="Terra",
    observed_at=T0 - timedelta(days=2),
    available_at=T0 - timedelta(days=2) + timedelta(hours=3),
)
AVAILABLE = T0 + timedelta(hours=3)
# The model gives each alert the value 0.5. Its reference alerts had the four values.
MODEL = {"inputs": ["x"], "mean": [0.0], "spread": [1.0], "start": 0.0, "weights": [0.0]}
MODEL |= {"reference": [0.1, 0.4, 0.6, 0.9]}
DAY = 86_400.0


@pytest.fixture(autouse=True)
def settings(monkeypatch, tmp_path):
    monkeypatch.setattr("chispa.config.RISK_CLASS_LIMITS_HA", (10.0, 100.0))
    monkeypatch.setattr("chispa.config.RISK_RANK_ONLY", ())
    monkeypatch.setattr("chispa.config.RISK_NOT_TESTED", (("24", 100.0),))
    monkeypatch.setattr("chispa.config.RISK_RECALIBRATION_DELAY_DAYS", 1)
    monkeypatch.setattr("chispa.config.RISK_RECALIBRATION_WINDOW_DAYS", 1000)
    monkeypatch.setattr("chispa.config.RISK_RECALIBRATION_PRIOR", 1.0)
    monkeypatch.setattr("chispa.config.RISK_NEAR_EARLIER_M", 1000.0)
    monkeypatch.setattr("chispa.config.RISK_NEAR_EARLIER_DAYS", 14)
    monkeypatch.setattr("chispa.config.RISK_LIVE_DAYS", 30)
    monkeypatch.setattr("chispa.config.RISK_LIVE_DIR", tmp_path / "risks")
    monkeypatch.setattr("chispa.config.RISK_MODELS_PATH", tmp_path / "risk_models.json")


def store_of(tmp_path, detections: list):
    """A store with the events of some detections. The ids start with the year 2024."""
    connection = open_store(tmp_path / "store.sqlite")
    add_detections(connection, detections)
    found = read_detections(connection, T0 - timedelta(days=30), T0 + timedelta(days=30))
    replace_fusion(connection, (FIRST_ID, FIRST_ID + 1000), fuse(found, first_id=FIRST_ID))
    return connection


def layers(south: float = -21.0) -> risk_live.Layers:
    """Layers with a biome that is a box from lat -15 to a south edge, and lon -60 to -55."""
    grid = Grid(west=-60.0, north=-15.0, pixel_deg=1.0, width=5, height=5)
    corners = [(-60.0, -15.0), (-55.0, -15.0), (-55.0, south), (-60.0, south), (-60.0, -15.0)]
    return risk_live.Layers(SimpleNamespace(grid=grid), [np.array(corners)], {})


def past(large: list[float]) -> dict:
    """Four older alerts on the days 0 to 3, each with the value 0.5, and their labels."""
    times = [0.0, DAY, 2 * DAY, 3 * DAY]
    return {"time": np.array(times), "value": np.full(4, 0.5), "large": np.array(large)}


def saved_of(large_10: list[float], large_100: list[float]) -> dict:
    names = [f"{moment}h_{limit}ha" for moment in ("0", "24") for limit in ("10", "100")]
    outcomes = {name: past(large_100 if "100" in name else large_10) for name in names}
    return {"models": dict.fromkeys(names, MODEL), "past": outcomes}


def test_chance_is_the_value_with_the_factor_of_the_known_outcomes():
    # 4 older alerts expected 2.0 large alerts. For 10 hectares 1 came: the factor is
    # (1 + 1) / (2 + 1) = 2/3, and the odds 1 become 2/3: the chance is 0.4.
    # For 100 hectares none came: the factor is 1/3, and the chance is 0.25.
    saved = saved_of([1.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 0.0])
    found = risk.limits(saved, {"x": 3.0}, "0", 10 * DAY)
    assert [one["limit_ha"] for one in found] == [10.0, 100.0]
    assert [one["chance"] for one in found] == [0.4, 0.25]
    assert [one["factor"] for one in found] == [0.6667, 0.3333]
    # 2 of the 4 reference alerts had a value below 0.5.
    assert [one["rank"] for one in found] == [0.5, 0.5]
    assert [one["not_tested"] for one in found] == [False, False]
    assert [one["not_tested"] for one in risk.limits(saved, {"x": 3.0}, "24", 10 * DAY)][1]


def test_alert_of_day_2_has_only_the_outcomes_that_are_one_day_old():
    # At the day 2 only the alerts of the days 0 and 1 are known: (1 + 1) / (1 + 1) = 1.
    saved = saved_of([1.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 0.0])
    assert risk.limits(saved, {"x": 0.0}, "0", 2 * DAY)[0]["chance"] == 0.5


def test_chance_of_a_larger_limit_is_not_above_that_of_a_smaller_limit(monkeypatch):
    # For 100 hectares each older alert became large: the factor is 5/3 and the value 0.625.
    # A fire of 100 hectares is also a fire of 10 hectares: the alert gets 0.4 for the two.
    saved = saved_of([1.0, 0.0, 0.0, 0.0], [1.0, 1.0, 1.0, 1.0])
    assert [one["chance"] for one in risk.limits(saved, {"x": 0.0}, "0", 10 * DAY)] == [0.4, 0.4]
    monkeypatch.setattr("chispa.config.RISK_RANK_ONLY", (("0", 100.0),))
    found = risk.limits(saved, {"x": 0.0}, "0", 10 * DAY)
    assert [one["chance"] for one in found] == [0.4, None]
    assert found[1]["rank"] == 0.5


def answer_of(moment: str, first: datetime = AVAILABLE) -> dict:
    at = first + timedelta(hours=0.5 if moment == "0" else 24)
    times = {"moment_at": to_text(at), "first_available_at": to_text(first)}
    return {"alert": FIRST_ID, "moment_h": moment, "limits": []} | times


def test_answer_of_an_alert_is_one_file_that_does_not_change(tmp_path):
    made = AVAILABLE + timedelta(minutes=31)
    path = risk_files.save(answer_of("0"), tmp_path, made)
    assert path == tmp_path / "2024" / f"{FIRST_ID}_0_20240815T080000.json"
    assert json.loads(path.read_text())["made_at"] == to_text(made)
    with pytest.raises(RuntimeError, match="does not change"):
        risk_files.save(answer_of("0"), tmp_path, made)


def test_record_has_the_answers_that_were_complete_at_the_as_of_time(tmp_path):
    seconds = int(AVAILABLE.timestamp())
    found = {"available": np.array([seconds, seconds + 60]), "issued": np.array([FIRST_ID] * 2)}
    risk_files.save(answer_of("0"), tmp_path, AVAILABLE + timedelta(hours=1))
    risk_files.save(answer_of("24"), tmp_path, AVAILABLE + timedelta(hours=25))
    assert risk_files.of_event(tmp_path, found, FIRST_ID, AVAILABLE + timedelta(minutes=40)) is None
    early = risk_files.of_event(tmp_path, found, FIRST_ID, AVAILABLE + timedelta(hours=2))
    assert list(early) == ["at_30_minutes"]
    late = risk_files.of_event(tmp_path, found, FIRST_ID, AVAILABLE + timedelta(hours=26))
    assert list(late) == ["at_30_minutes", "at_24_hours"]
    # After new older rows in the store, the id can be the id of a different alert: its first
    # detection has a different time. The files are then not files of this alert, and the
    # alert gets its own file with the same id.
    other = found | {"available": found["available"] + 3600}
    assert risk_files.of_event(tmp_path, other, FIRST_ID, AVAILABLE + timedelta(hours=26)) is None
    later = AVAILABLE + timedelta(hours=1)
    path = risk_files.save(answer_of("0", first=later), tmp_path, later + timedelta(hours=1))
    assert path.name == f"{FIRST_ID}_0_20240815T090000.json"
    again = risk_files.of_event(tmp_path, other, FIRST_ID, AVAILABLE + timedelta(hours=26))
    assert again["at_30_minutes"]["first_available_at"] == to_text(later)


def test_saved_models_are_only_those_of_the_settings_of_now(tmp_path, monkeypatch):
    path = tmp_path / "risk_models.json"
    assert risk_files.load_models(path) is None
    risk_files.save_models({"models": {}}, path)
    assert risk_files.load_models(path)["models"] == {}
    monkeypatch.setattr(risk_files, "config_hash", lambda: "other settings")
    assert risk_files.load_models(path) is None


def test_alert_is_due_when_its_moment_came_and_it_has_no_file(tmp_path):
    store = store_of(tmp_path, [VIIRS, FAR])
    folder, first = tmp_path / "risks", int(AVAILABLE.timestamp())
    # The two alerts were available 3 hours after T0. The first moment is 30 minutes later.
    assert risk_live.due(store, AVAILABLE + timedelta(minutes=29), folder) == []
    found = risk_live.due(store, AVAILABLE + timedelta(minutes=30), folder)
    assert found == [(FIRST_ID, "0", first), (FIRST_ID + 1, "0", first)]
    risk_files.save(answer_of("0"), folder, AVAILABLE + timedelta(minutes=31))
    later = risk_live.due(store, AVAILABLE + timedelta(hours=24), folder)
    assert later == [
        (FIRST_ID, "24", first),
        (FIRST_ID + 1, "0", first),
        (FIRST_ID + 1, "24", first),
    ]
    # A moment of more than 30 days before now gets no answer.
    assert risk_live.due(store, AVAILABLE + timedelta(days=31, hours=1), folder) == []


def test_alert_near_a_detection_of_an_earlier_alert_has_the_mark(tmp_path, monkeypatch):
    store = store_of(tmp_path, [EARLIER, VIIRS])
    at = AVAILABLE + timedelta(minutes=30)
    found = risk_live.event_at(store, FIRST_ID + 1, at, layers())
    assert found["issued"].tolist() == [FIRST_ID + 1]
    mark = risk_live.near_earlier(store, found, FIRST_ID + 1, layers())
    assert (mark["alert"], mark["hours_before"], mark["detections"]) == (FIRST_ID, 48.0, 1)
    assert 495 <= mark["distance_m"] <= 505
    assert mark["sensor_families"] == ["modis"]
    # The earlier alert itself has no detection before it.
    first = risk_live.event_at(store, FIRST_ID, at - timedelta(days=2), layers())
    assert risk_live.near_earlier(store, first, FIRST_ID, layers()) is None
    monkeypatch.setattr("chispa.config.RISK_NEAR_EARLIER_DAYS", 1)
    assert risk_live.near_earlier(store, found, FIRST_ID + 1, layers()) is None
    monkeypatch.setattr("chispa.config.RISK_NEAR_EARLIER_DAYS", 14)
    monkeypatch.setattr("chispa.config.RISK_NEAR_EARLIER_M", 400.0)
    assert risk_live.near_earlier(store, found, FIRST_ID + 1, layers()) is None


def test_alert_that_did_not_start_in_the_biome_has_no_answer(tmp_path):
    store = store_of(tmp_path, [VIIRS])
    # The detection is at lat -17.5, and this biome ends at lat -17.
    outside = layers(south=-17.0)
    found = risk_live.event_at(store, FIRST_ID, AVAILABLE + timedelta(minutes=30), outside)
    assert found == risk_live.NOT_FIRST


def weather_days(count: int, later: dict | None = None) -> risk_weather.Days:
    """ERA5-Land days from 2024-05-01 for a grid of one cell: 1 mm of rain on each day."""
    names = ("wind_kmh", "vpd_kpa", "temp_c", "rain_mm")
    era5 = {name: np.ones((count, 1, 1)) for name in names}
    return risk_weather.Days(date(2024, 5, 1), era5, later or {}, None)


def test_days_that_era5_land_does_not_have_come_from_open_meteo(tmp_path, monkeypatch):
    names = ("wind_kmh", "vpd_kpa", "temp_c", "rain_mm")
    on_disk = {name: np.ones((10, 3, 3)) for name in names}
    monkeypatch.setattr("chispa.sources.weather.read_newest", lambda *_: (on_disk, None))
    asked = []

    def download(lats, lons, days, raw_dir):
        asked.append((lats.tolist(), lons.tolist(), days))
        return tmp_path / "answer.json"

    monkeypatch.setattr("chispa.sources.openmeteo.download", download)
    more = {name: np.full((1, 2), 7.0) for name in names}
    monkeypatch.setattr("chispa.sources.openmeteo.read", lambda path: (more, None))
    # The files have the 10 days from 1 to 10 May. An alert needs the days to 10 May: no request.
    days = risk_weather.load(tmp_path, date(2024, 5, 3), date(2024, 5, 10), {(1, 2)}, None)
    assert (days.start, days.later, asked) == (date(2024, 5, 1), {}, [])
    assert risk_weather.series(days, (1, 2))[1] == 10
    # An alert needs the days to 12 May: the two last days come from Open-Meteo, for its cell.
    days = risk_weather.load(tmp_path, date(2024, 5, 3), date(2024, 5, 12), {(1, 2)}, None)
    assert asked[0][2] == (date(2024, 5, 11), date(2024, 5, 12))
    series, era5 = risk_weather.series(days, (1, 2))
    assert (era5, series["rain_mm"].tolist()) == (10, [1.0] * 10 + [7.0, 7.0])
    # An alert of 8 May needs the days to 1 May only: the files have more days than that.
    days = risk_weather.load(tmp_path, date(2024, 5, 1), date(2024, 5, 1), {(1, 2)}, None)
    assert len(risk_weather.series(days, (1, 2))[0]["rain_mm"]) == 1


def test_weather_inputs_of_an_alert_stop_some_days_before_its_day(monkeypatch):
    monkeypatch.setattr("chispa.config.RISK_RAIN_DAYS", (2, 4))
    monkeypatch.setattr(risk, "RAIN", ("rain_2d_log", "rain_4d_log"))
    monkeypatch.setattr("chispa.config.RISK_WEATHER_DAYS", 2)
    monkeypatch.setattr("chispa.config.RISK_WEATHER_LATE_DAYS", 6)
    # An alert of 11 May: the inputs are those of the days before 5 May, which is the day 4.
    one = {"cell": (0, 0), "day": date(2024, 5, 11)}
    late = risk_live.late_weather(dict(one), weather_days(4))
    assert late["rain_2d_log_late"] == pytest.approx(np.log1p(2.0))
    assert late["rain_4d_log_late"] == pytest.approx(np.log1p(4.0))
    # With 3 days on disk and 1 day of Open-Meteo, the alert has 1 day that is not ERA5-Land.
    more = {name: np.array([np.nan]) for name in ("wind_kmh", "vpd_kpa", "temp_c", "rain_mm")}
    with_more = dict(one)
    assert risk_live.late_weather(with_more, weather_days(3, {(0, 0): more})) is None
    assert with_more["weather_open_meteo_days"] == 1
    with pytest.raises(RuntimeError, match="does not have each day"):
        risk_live.late_weather(dict(one), weather_days(3))


def save_models(checked: datetime) -> None:
    made = {"made_at": to_text(checked), "map_checked_at": to_text(checked), "map": {"2024": 6}}
    risk_files.save_models(made | saved_of([0.0] * 4, [0.0] * 4) | {"past": {}}, _models_path())


def _models_path():
    from chispa import config

    return config.RISK_MODELS_PATH


def test_saved_models_are_made_again_one_time_each_day(tmp_path):
    store_of(tmp_path, [VIIRS])
    now, calls = AVAILABLE + timedelta(hours=1), []

    def refresh(store_path, raw_dir, time, project):
        calls.append(project)
        return "The Monitor map has no new month."

    paths = (tmp_path / "store.sqlite", tmp_path)
    # No file and no project of Earth Engine: nothing can make the file.
    assert "Add EE_PROJECT" in risk_live.keep_current(*paths, now, (None, refresh))
    line = risk_live.update(*paths, now, (None, refresh))
    assert line == (
        "growth risk: no saved models. Add EE_PROJECT to the file .env: an update then makes them."
    )
    # No file: the function of the evaluation makes it.
    assert risk_live.keep_current(*paths, now, ("project", refresh)).startswith("The Monitor map")
    save_models(now - timedelta(hours=1))
    assert risk_live.keep_current(*paths, now, ("project", refresh)) is None
    save_models(now - timedelta(hours=25))
    risk_live.keep_current(*paths, now, ("project", refresh))
    assert calls == ["project", "project"]


def test_failed_look_for_a_new_month_keeps_the_saved_models(tmp_path):
    def refresh(store_path, raw_dir, time, project):
        raise RuntimeError("Earth Engine gave no answer.")

    save_models(AVAILABLE - timedelta(hours=25))
    note = risk_live.keep_current(tmp_path, tmp_path, AVAILABLE, ("project", refresh))
    assert note == "The saved models are not new. Earth Engine gave no answer."
    # The models stay, and the next look is one day later: not in the next update.
    assert risk_files.load_models(_models_path())["map_checked_at"] == to_text(AVAILABLE)


def test_update_gives_each_new_alert_its_file_and_the_record_reads_it(tmp_path, monkeypatch):
    store = store_of(tmp_path, [EARLIER, VIIRS])
    save_models(AVAILABLE)
    monkeypatch.setattr(risk_live, "load_layers", lambda raw_dir, year: layers())
    monkeypatch.setattr(risk_live, "inputs", lambda *_: {"x": 1.0})
    monkeypatch.setattr(risk_weather, "load", lambda *_: weather_days(400))
    monkeypatch.setattr(risk_weather, "series", lambda *_: ({"rain_mm": np.ones(400)}, 400))
    monkeypatch.setattr("chispa.risk.late_weather_inputs", lambda series, today: {"rain": 0.0})
    saved = json.loads(_models_path().read_text())
    saved["past"] = {name: {"time": [], "value": [], "large": []} for name in saved["models"]}
    _models_path().write_text(json.dumps(saved))
    now = AVAILABLE + timedelta(hours=1)
    line = risk_live.update(tmp_path / "store.sqlite", tmp_path, now, (None, None))
    # The alert of 2 days before is older than its two moments in the window, with no file:
    # it gets its two files, and the new alert gets the file of its first moment.
    assert line == "growth risk: 3 new files, 2 with a percentage."
    assert risk_live.update(tmp_path / "store.sqlite", tmp_path, now, (None, None)) == (
        "growth risk: 0 new files, 0 with a percentage."
    )
    found = record.read(store, [FIRST_ID + 1], now)
    answer = risk_files.of_event(tmp_path / "risks", found, FIRST_ID + 1, datetime.now(UTC))
    first = answer["at_30_minutes"]
    assert (first["no_percentage"], first["near_earlier"]["alert"]) == (
        risk_live.NEAR_EARLIER,
        FIRST_ID,
    )
    # No older alert has a known outcome: the factor is 1, and the value 0.5 stays.
    assert [limit["chance"] for limit in first["limits"]] == [None, None]
    assert [limit["rank"] for limit in first["limits"]] == [0.5, 0.5]
    other = record.read(store, [FIRST_ID], now)
    older = risk_files.of_event(tmp_path / "risks", other, FIRST_ID, datetime.now(UTC))
    assert [limit["chance"] for limit in older["at_24_hours"]["limits"]] == [0.5, 0.5]
    # The file has the inputs of the answer. The record does not.
    assert "inputs" not in older["at_24_hours"]
    first_s = int((AVAILABLE - timedelta(days=2)).timestamp())
    saved = json.loads(risk_files.path_of(tmp_path / "risks", FIRST_ID, "24", first_s).read_text())
    assert saved["inputs"] == {"x": 1.0, "rain": 0.0}


def test_ground_of_the_year_before_can_come_from_the_monitor_map(tmp_path, monkeypatch):
    grid = Grid(west=-60.0, north=-15.0, pixel_deg=0.1, width=20, height=20)
    monkeypatch.setattr(risk, "pantanal_grid", lambda: grid)
    monkeypatch.setattr(risk, "layer_grid", lambda: Grid(-60.0, -15.0, 1.0, 2, 2))
    monkeypatch.setattr("chispa.config.LAYER_CELLS", 10)
    monkeypatch.setattr("chispa.config.RISK_BURNED_YEARS", 2)
    monkeypatch.setattr("chispa.config.RISK_TEST_YEAR", 2026)
    # The Monitor map of 2026: 50 of the 100 pixels of the north-west cell burned, in March.
    months = np.zeros((20, 20), dtype=np.uint8)
    months[:5, :10] = 3
    monkeypatch.setattr("chispa.sources.monitor.read_year", lambda year, raw, grid: (months, 10))
    (tmp_path / "burned").mkdir()
    annual = np.array([[20, 0], [0, 100]], dtype=np.uint8)
    np.savez_compressed(tmp_path / "burned" / "2025.npz", percent=annual)
    # 2026 has no annual map. An alert of 2027 gets the share of 2026 from the Monitor map.
    share = risk.burned_share(tmp_path, 2026, monitor_map=True)
    assert share.tolist() == [[0.5, 0.0], [0.0, 0.0]]
    # A year with its annual map on disk keeps that map.
    with_annual = risk.burned_share(tmp_path, 2025, monitor_map=True)
    assert np.allclose(with_annual, [[0.2, 0.0], [0.0, 1.0]])
    ground = risk.ground_before(tmp_path, 2027)
    # The north-west cell burned in the year before: 1 year. The south-east cell: 2 years.
    assert np.exp(ground["burned_years_log"]).round().tolist() == [[1.0, 3.0], [3.0, 2.0]]
    # A year to the test year must have each annual map: the test read those maps.
    with pytest.raises(RuntimeError, match="fetch burned --year 2024"):
        risk.ground_before(tmp_path, 2026)
