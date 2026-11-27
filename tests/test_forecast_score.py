"""Tests of the score of the saved live forecasts, with cases small enough for paper."""

import csv
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pytest
from scipy.spatial import cKDTree

from chispa import forecast_files, fronts
from chispa.evaluation import forecast_score
from chispa.evaluation import fronts as steps
from chispa.store import open_store, save_log_size, to_text

LAT, LON = -19.0, -57.0
EAST = 1 / (111_320 * np.cos(np.deg2rad(19.0)))  # One metre east in degrees, at the box centre.
LOOK = datetime(2023, 9, 1, 5, 0, tzinfo=UTC)
SEEN = 1


@pytest.fixture(autouse=True)
def fixed_values(monkeypatch):
    monkeypatch.setattr("chispa.config.LOOK_GAP", timedelta(hours=3))
    monkeypatch.setattr("chispa.config.FRONT_LINK_M", 1500.0)
    monkeypatch.setattr("chispa.config.FRONT_WINDOWS_H", {12: (6, 18), 24: (6, 30)})
    monkeypatch.setattr("chispa.config.FRONT_REACH_M", {12: 5000.0, 24: 8000.0})
    monkeypatch.setattr("chispa.config.FRONT_MASK_HOURS", 2)
    monkeypatch.setattr("chispa.config.FRONT_HIDDEN_SHARE", 0.5)
    monkeypatch.setattr("chispa.config.GROWTH_FLOOR_M", 850.0)
    monkeypatch.setattr("chispa.config.FRONT_SMALL_BELOW", 3)
    monkeypatch.setattr("chispa.config.FRONT_DIRECTION_PIXELS", 3)
    monkeypatch.setattr("chispa.config.FRONT_SECTORS", 8)
    monkeypatch.setattr("chispa.config.ADVANCE_SAME_DEG", 45.0)
    monkeypatch.setattr("chispa.config.LIVE_START", datetime(2023, 1, 1, tzinfo=UTC))
    monkeypatch.setattr("chispa.config.LIVE_PASS_END_FROM", datetime(2023, 1, 1, tzinfo=UTC))
    monkeypatch.setattr("chispa.config.LIVE_POLL_LATE", timedelta(minutes=15))
    monkeypatch.setattr("chispa.config.LIVE_LOOKBACK", timedelta(days=4))


def store_of(tmp_path, pixels: list[tuple[float, float, float]]):
    """A store with VIIRS pixels: (hours after the look, hours to available, metres east)."""
    store = open_store(tmp_path / "store.sqlite")
    for number, (hours, late, east) in enumerate(pixels, start=1):
        at = LOOK + timedelta(hours=hours)
        times = (to_text(at), to_text(at + timedelta(hours=late)))
        place = (LAT, LON + east * EAST)
        row = (number, "firms", "viirs", "NOAA20", *times, *place, 375.0, 5.0, "nominal", 1)
        store.execute("INSERT INTO detections VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", row)
    store.commit()
    return store


# A front of three pixels in a row to the east at 05:00, available at 08:00.
FRONT = [(0, 3, 0.0), (0, 3, 400.0), (0, 3, 800.0)]
# Three pixels 12 hours later, 2000 m and more to the east of the front: new ground.
NEW = [(12, 3, 2800.0), (12, 3, 3200.0), (12, 3, 3600.0)]


def masks_of() -> steps.Masks:
    """One GOES pixel at the front. GOES examined it at 17:00 and at 05:00 of the next day."""
    tree = cKDTree(fronts.metres(np.array([LAT]), np.array([LON + 400 * EAST])))
    days = {}
    for day, hour in ((date(2023, 9, 1), 17), (date(2023, 9, 2), 5)):
        midnight = datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp()
        days[day] = (np.array([midnight + hour * 3600]), np.array([[SEEN]], dtype=np.uint8))
    return steps.Masks(None, tree, days)


def window(hours: int, chance: float | None, east: float = 0.3) -> dict:
    """A window of a file from 6 hours after the look, with a chance to the east only."""
    limits = {"from": (LOOK + timedelta(hours=6)).isoformat(timespec="minutes")}
    limits["to"] = (LOOK + timedelta(hours=6 + hours)).isoformat(timespec="minutes")
    sectors = dict.fromkeys(("north", "north-east", "east", "south-east"), 0.0)
    sectors |= dict.fromkeys(("south", "south-west", "west", "north-west"), 0.0) | {"east": east}
    none = chance is None
    limits |= {"new_ground": chance, "large_growth": None if none else 0.01}
    return limits | {"sectors": None if none else sectors}


def saved_of(pixels: int = 3, chance: float | None = 0.4) -> dict:
    """The forecast of the front: made at 08:31 with the pixels to 08:30."""
    front = {"lat": LAT, "lon": round(LON + 400 * EAST, 4), "pixels": pixels, "events": [7]}
    front |= {"hours_12": window(12, chance), "hours_24": window(24, chance)}
    times = {"look_at": LOOK.isoformat(timespec="minutes"), "trees": "mark"}
    times["pixels_to"] = to_text(LOOK + timedelta(hours=3.5))
    times["made_at"] = to_text(LOOK + timedelta(hours=3, minutes=31))
    return times | {"large_growth_pixels": 10, "fronts": [front]}


def test_a_front_of_a_file_gets_the_answer_of_the_later_pixels(tmp_path):
    store = store_of(tmp_path, FRONT + NEW)
    seen = forecast_score.as_seen(store, saved_of())
    assert seen[1] == (0, 3) and len(seen[0]["seconds"]) == 6
    answers = forecast_score.front_answers(saved_of(), seen, masks_of())
    # Three new pixels in the window of 12 hours, and the same three in the window of 24 hours.
    assert (int(answers["new_12"][0]), int(answers["new_24"][0])) == (3, 3)
    assert steps.ANSWERS[int(answers["answer_12"][0])] == "new_ground"
    assert bool(answers["examined_12"][0]) and bool(answers["examined_24"][0])
    # Each new pixel is to the east of the nearest pixel of the front: 90 degrees.
    assert round(float(answers["direction_deg_12"][0]), 1) == 90.0
    # No pixel before the look: 0 pixels came from known ground, and 3 are far from it.
    assert round(float(answers["persistence"][0]), 4) == round(float(np.log1p(3)), 4)


def test_a_pixel_of_the_look_that_came_after_the_file_gives_no_score(tmp_path):
    # A fourth pixel of the pass was available at 10:00. The file had the pixels to 08:30.
    store = store_of(tmp_path, [*FRONT, (0, 5, 1200.0), *NEW])
    assert forecast_score.as_seen(store, saved_of()) is None
    # The store has no pixel that was available at the time of the file.
    late = store_of(tmp_path / "late", [(0, 5, 0.0)])
    assert forecast_score.as_seen(late, saved_of()) is None


def test_a_front_of_the_file_that_is_not_in_the_look_gives_no_answers(tmp_path):
    store = store_of(tmp_path, FRONT + NEW)
    seen = forecast_score.as_seen(store, saved_of())
    # The file says 4 pixels, and the look has a front of 3 pixels at that place.
    assert forecast_score.front_answers(saved_of(pixels=4), seen, masks_of()) is None


def test_the_forecast_of_a_look_is_its_newest_file_before_the_first_window(tmp_path):
    def save(look_at: datetime, pixels: int, hours: float) -> None:
        look = saved_of(pixels) | {"look_at": look_at.isoformat(timespec="minutes")}
        forecast_files.save([look], tmp_path, look_at + timedelta(hours=hours))

    # The first window starts 6 hours after the look. A file of that moment or later is too late.
    for pixels, hours in ((3, 3.5), (5, 4.5), (6, 6.0), (7, 7.0)):
        save(LOOK, pixels, hours)
    # A look with only a late file, and a look of 31 December: its windows end in the next year.
    save(LOOK + timedelta(hours=12), 3, 6.5)
    save(datetime(2023, 12, 31, 17, 0, tzinfo=UTC), 3, 1.0)
    found = forecast_score.issued(tmp_path, 2023)
    assert [(one["look_at"], one["fronts"][0]["pixels"]) for one in found] == [
        ("2023-09-01T05:00+00:00", 5)
    ]


def poller(raw_dir, passes: list[tuple[float, str]]) -> None:
    """Write the poll log: (hours after the look, the result of FIRMS) for each pass."""
    days: dict[str, list[str]] = {}
    for hours, result in passes:
        at = (LOOK + timedelta(hours=hours)).isoformat()
        rows = days.setdefault(at[:10], ["polled_at,source,item,result,new_rows"])
        rows += [f"{at},firms,VIIRS_NOAA20_NRT,{result},0", f"{at},pass,end,ok,0"]
    folder = raw_dir / "live" / "polls"
    folder.mkdir(parents=True, exist_ok=True)
    for day, rows in days.items():
        (folder / f"{day}.csv").write_text("\n".join(rows) + "\n")


def test_a_window_has_an_answer_only_if_a_pass_of_the_poller_can_give_it(tmp_path):
    # The window of 12 hours is from 6 to 18 hours after the look. Its answer needs a pass with
    # no failure from 24 hours after the look, to 4 days after the start of the window.
    window, late = saved_of()["fronts"][0]["hours_12"], LOOK + timedelta(hours=200)
    assert not forecast_score.answered(tmp_path, window, late)  # The poller has no pass.
    poller(tmp_path / "early", [(23, "ok")])
    assert not forecast_score.answered(tmp_path / "early", window, late)
    poller(tmp_path / "failed", [(23, "ok"), (24, "HTTP 500")])
    assert not forecast_score.answered(tmp_path / "failed", window, late)
    poller(tmp_path / "read", [(23, "ok"), (24, "ok")])
    assert forecast_score.answered(tmp_path / "read", window, late)
    # Half an hour before that pass, the answer is not there.
    assert not forecast_score.answered(tmp_path / "read", window, LOOK + timedelta(hours=23.5))
    # A stop of the poller: the next pass is 103 hours after the look. The read-back of 4 days
    # from that pass starts after the start of the window: its pixels are lost.
    poller(tmp_path / "stop", [(23, "ok"), (103, "ok")])
    assert not forecast_score.answered(tmp_path / "stop", window, late)
    poller(tmp_path / "back", [(23, "ok"), (101, "ok")])
    assert forecast_score.answered(tmp_path / "back", window, late)


def test_a_window_has_a_row_when_it_has_an_answer(tmp_path):
    store = store_of(tmp_path, FRONT + NEW)
    saved = saved_of()
    answers = forecast_score.front_answers(saved, forecast_score.as_seen(store, saved), masks_of())
    poller(tmp_path, [(hours, "ok") for hours in range(41)])  # One pass each hour.

    def table(forecast: dict, came: dict | None, hours: float) -> list[dict]:
        return forecast_score.front_table(forecast, came, tmp_path, LOOK + timedelta(hours=hours))

    # The window of 12 hours ends 18 hours after the look. 5 hours later is too early.
    assert table(saved, answers, 23) == []
    (row,) = table(saved, answers, 24)
    assert (row["hours"], row["pixels"], row["new_ground"], row["trees"]) == (12, 3, 0.4, "mark")
    assert (row["same_look"], row["examined"], row["answer"]) == (True, True, "new_ground")
    assert (row["new_pixels"], row["forecast_direction_deg"], row["direction_deg"]) == (3, 90, 90)
    # 36 hours after the look, the window of 24 hours has its row also.
    assert [one["hours"] for one in table(saved, answers, 36)] == [12, 24]
    # A look with no answers has its rows, with no answer in them.
    (row,) = table(saved, None, 24)
    assert (row["same_look"], row["examined"], row["answer"]) == (False, None, None)
    # A front with no chance has no row.
    assert table(saved_of(chance=None), answers, 36) == []


def row_of(chance: float, new: int, persistence: float, examined: bool | None = True) -> dict:
    row = {"look_at": "a", "hours": 12, "pixels": 5, "new_ground": chance, "new_pixels": new}
    row |= {"same_look": examined is not None, "examined": examined, "persistence": persistence}
    return row | {"forecast_direction_deg": 90.0, "direction_deg": 100.0 if new else None}


def test_the_summary_scores_only_the_fronts_that_goes_examined():
    # Four examined fronts. New ground came for the chances 0.9 and 0.2, not for 0.8 and 0.1.
    table = [row_of(0.9, 3, 2.0), row_of(0.8, 0, 1.0), row_of(0.2, 1, 0.0), row_of(0.1, 0, 0.0)]
    # One front that GOES did not examine, and one front of a look with no answers.
    table += [row_of(0.7, 4, 3.0, False), row_of(0.6, 0, 0.0, None)]
    large, small = forecast_score.summary(table)[:2]
    assert (large["hours"], large["size"], large["looks"], large["fronts"]) == (
        12,
        "3 or more",
        1,
        6,
    )
    assert (large["same_look"], large["examined"], large["new_ground"]) == (5, 4, 2)
    assert large["chance_sum"] == 2.0
    # Of the 4 pairs of a front with new ground and a front with none, 3 have the larger chance.
    assert large["auc_trees"] == 0.75
    # Persistence: 2 pairs are in sequence, 1 is not, and 1 has the same value: 2.5 of 4.
    assert large["auc_persistence"] == 0.625
    # One examined front has 3 new pixels: its direction is 10 degrees from the forecast.
    assert (large["fronts_with_direction"], large["trees_in_45"]) == (1, 1)
    assert (small["fronts"], small["examined"], small["auc_trees"]) == (0, 0, None)


def test_the_command_stops_if_the_store_did_not_read_each_row_of_a_firms_log(tmp_path):
    store = open_store(tmp_path / "store.sqlite")
    forecast_score.check_store(store, tmp_path)  # No log on disk: nothing to read.
    log = tmp_path / "live" / "firms" / "VIIRS_NOAA20_NRT" / "2023-09-02.csv"
    log.parent.mkdir(parents=True)
    log.write_text("one row\n")
    # The log has a row that the store did not read: the answers can be wrong.
    with pytest.raises(RuntimeError, match="Run `chispa update`"):
        forecast_score.check_store(store, tmp_path)
    save_log_size(store, "live/firms/VIIRS_NOAA20_NRT/2023-09-02.csv", log.stat().st_size)
    forecast_score.check_store(store, tmp_path)


def test_the_command_saves_the_rows_and_gives_the_table_of_each_year(tmp_path, monkeypatch):
    monkeypatch.setattr("chispa.config.FORECAST_LIVE_DIR", tmp_path / "forecasts")
    monkeypatch.setattr("chispa.config.RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(steps, "masks_in", lambda raw_dir: masks_of())
    poller(tmp_path, [(hours, "ok") for hours in range(41)])  # One pass each hour.
    store_of(tmp_path, FRONT + NEW).close()
    forecast_files.save([saved_of()], tmp_path / "forecasts", LOOK + timedelta(hours=3.5))
    path = tmp_path / "store.sqlite"
    # 20 hours after the look, no window has an answer: no table and no file.
    assert forecast_score.score_tables(path, tmp_path, LOOK + timedelta(hours=20)) == {}
    assert not (tmp_path / "results").exists()
    tables = forecast_score.score_tables(path, tmp_path, LOOK + timedelta(hours=24))
    (row,) = [row for row in tables[2023]["forecast_live"] if row["fronts"]]
    assert (row["hours"], row["examined"], row["new_ground"], row["chance_sum"]) == (12, 1, 1, 0.4)
    # One front has no pair: no AUC.
    assert row["auc_trees"] is None and row["trees_in_45"] == 1
    with (tmp_path / "results" / "2023" / "forecast_live" / "fronts.csv").open() as file:
        (saved,) = list(csv.DictReader(file))
    assert (saved["look_at"], saved["answer"]) == ("2023-09-01T05:00+00:00", "new_ground")
