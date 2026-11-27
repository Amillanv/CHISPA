"""Tests of the files of the live growth forecast, with cases small enough for paper."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from chispa import forecast_files

LOOK = datetime(2026, 11, 25, 17, 19, tzinfo=UTC)


@pytest.fixture(autouse=True)
def fixed_values(monkeypatch):
    monkeypatch.setattr("chispa.config.FRONT_WINDOWS_H", {12: (6, 18), 24: (6, 30)})
    monkeypatch.setattr("chispa.config.FRONT_SMALL_BELOW", 3)


def text(time: datetime) -> str:
    return time.isoformat(timespec="minutes")


def after(hours: float, look_at: datetime = LOOK) -> datetime:
    return look_at + timedelta(hours=hours)


def front(pixels: int, events: list[int], look_at: datetime = LOOK, chance: bool = True) -> dict:
    """A front with the two windows of its look, and a chance for each of two sectors."""
    found = {"lat": -17.35, "lon": -57.24, "pixels": pixels, "events": events}
    for hours, high in ((12, 18), (24, 30)):
        window = {"from": text(after(6, look_at)), "to": text(after(high, look_at))}
        window |= {"new_ground": 0.2, "large_growth": 0.05, "sectors": {"north": 0.1, "east": 0.02}}
        if not chance:
            window |= dict.fromkeys(("new_ground", "large_growth", "sectors"))
        found[f"hours_{hours}"] = window
    return found if chance else found | {"no_forecast": "no weather before the look"}


def look_of(fronts: list[dict], look_at: datetime = LOOK) -> dict:
    """The forecast of a look as `forecast_live.py` makes it. A large growth is 10 new pixels."""
    times = {"look_at": text(look_at), "pixels_to": text(look_at)}
    return times | {"large_growth_pixels": 10, "fronts": fronts}


def test_the_first_forecast_of_a_look_stays_when_a_newer_one_comes(tmp_path):
    first = forecast_files.save([look_of([front(9, [7])])], tmp_path, after(3))
    assert [path.name for path in first] == ["2026-11-25T1719_2026-11-25T201900.json"]
    assert json.loads(first[0].read_text())["made_at"] == "2026-11-25T20:19:00+00:00"
    # The same look again with the same pixels: no new file.
    assert forecast_files.save([look_of([front(9, [7])])], tmp_path, after(3.1)) == []
    assert not forecast_files.is_new(tmp_path, text(LOOK), 9)
    # A second satellite gave more pixels: a new file, and the first file stays as it was.
    assert forecast_files.is_new(tmp_path, text(LOOK), 12)
    second = forecast_files.save([look_of([front(12, [7])])], tmp_path, after(4))
    assert [path.name for path in second] == ["2026-11-25T1719_2026-11-25T211900.json"]
    assert json.loads(first[0].read_text())["fronts"][0]["pixels"] == 9
    assert forecast_files.save([look_of([front(12, [7])])], tmp_path, after(4.1)) == []
    assert sorted(path.name for path in tmp_path.iterdir()) == [first[0].name, second[0].name]


def test_two_forecasts_of_one_look_in_one_minute_are_two_files(tmp_path):
    made = after(3)
    forecast_files.save([look_of([front(9, [7])])], tmp_path, made)
    later = forecast_files.save([look_of([front(12, [7])])], tmp_path, made + timedelta(seconds=20))
    assert [path.name for path in later] == ["2026-11-25T1719_2026-11-25T201920.json"]
    # In the same second, the second forecast does not go away in silence.
    with pytest.raises(RuntimeError, match="a forecast file does not change"):
        forecast_files.save([look_of([front(15, [7])])], tmp_path, made + timedelta(seconds=20))


def test_a_forecast_with_a_chance_comes_after_one_with_no_chance(tmp_path):
    # The first forecast of the look had no weather: its front has no chance.
    forecast_files.save([look_of([front(4, [7], chance=False)])], tmp_path, after(3))
    assert (
        forecast_files.of_event(tmp_path, [7], after(4))["fronts"][0]["hours_12"]["new_ground"]
        is None
    )
    # The weather came. The front has the same pixels, and now a chance: the look gets a new file.
    assert len(forecast_files.save([look_of([front(4, [7])])], tmp_path, after(5))) == 1
    assert (
        forecast_files.of_event(tmp_path, [7], after(6))["fronts"][0]["hours_12"]["new_ground"]
        == 0.2
    )


def test_a_forecast_from_other_trees_comes_after_the_first_one(tmp_path):
    first = look_of([front(4, [7])]) | {"trees": "mark of the trees before"}
    second = look_of([front(4, [7])]) | {"trees": "mark of the new trees"}
    second["fronts"][0]["hours_12"]["new_ground"] = 0.25
    forecast_files.save([first], tmp_path, after(3))
    # The same pixels and the same trees: no new file. Other trees: a new file for the look.
    assert forecast_files.save([first], tmp_path, after(4)) == []
    assert len(forecast_files.save([second], tmp_path, after(5))) == 1
    assert forecast_files.save([second], tmp_path, after(6)) == []
    # The record has the forecast that existed at its time.
    assert (
        forecast_files.of_event(tmp_path, [7], after(4))["fronts"][0]["hours_12"]["new_ground"]
        == 0.2
    )
    assert (
        forecast_files.of_event(tmp_path, [7], after(6))["fronts"][0]["hours_12"]["new_ground"]
        == 0.25
    )


def test_an_event_gets_the_fronts_with_one_of_its_issued_ids(tmp_path):
    # The look has a front of 4 pixels of the alert 7, and a front of 1 pixel of the alert 9.
    forecast_files.save([look_of([front(4, [7]), front(1, [9])])], tmp_path, after(3))
    found = forecast_files.of_event(tmp_path, [7], after(4))
    assert (found["look_at"], found["made_at"]) == (text(LOOK), "2026-11-25T20:19:00+00:00")
    assert found["large_growth_pixels"] == 10 and len(found["fronts"]) == 1
    assert found["fronts"][0]["pixels"] == 4 and "events" not in found["fronts"][0]
    assert found["fronts"][0]["hours_12"]["sectors"] == {"north": 0.1, "east": 0.02}
    # The alert 8 merged into an event that also has the alert 7: the event has the front.
    assert forecast_files.of_event(tmp_path, [8, 7], after(4))["fronts"][0]["pixels"] == 4
    assert forecast_files.of_event(tmp_path, [5], after(4)) is None


def test_the_record_gives_the_minimum_of_a_large_growth_of_the_day_of_the_forecast(
    tmp_path, monkeypatch
):
    forecast_files.save([look_of([front(4, [7])])], tmp_path, after(3))
    # The configuration changes after the forecast. Its chance is for 10 pixels: the record says 10.
    monkeypatch.setattr("chispa.config.FRONT_LARGE_PIXELS", 20)
    assert forecast_files.of_event(tmp_path, [7], after(4))["large_growth_pixels"] == 10


def test_a_small_front_has_its_chance_and_no_sectors(tmp_path):
    forecast_files.save([look_of([front(4, [7]), front(1, [9])])], tmp_path, after(3))
    small = forecast_files.of_event(tmp_path, [9], after(4))["fronts"][0]
    assert small["hours_12"]["new_ground"] == 0.2 and small["hours_12"]["sectors"] is None
    assert small["hours_24"]["sectors"] is None


def test_the_record_has_only_a_file_that_was_complete_at_its_time(tmp_path):
    forecast_files.save([look_of([front(4, [7])])], tmp_path, after(3))
    forecast_files.save([look_of([front(6, [7])])], tmp_path, after(5))
    # One second before the first file was complete, the record has no forecast.
    assert forecast_files.of_event(tmp_path, [7], after(3) - timedelta(seconds=1)) is None
    assert forecast_files.of_event(tmp_path, [7], after(3))["fronts"][0]["pixels"] == 4
    assert forecast_files.of_event(tmp_path, [7], after(4))["fronts"][0]["pixels"] == 4
    assert forecast_files.of_event(tmp_path, [7], after(6))["fronts"][0]["pixels"] == 6
    # A file that is not complete has a different name: the record does not read it.
    (tmp_path / "2026-11-25T1719_2026-11-25T231900.json.part").write_text("{")
    assert forecast_files.of_event(tmp_path, [7], after(7))["fronts"][0]["pixels"] == 6


def test_a_window_that_ended_is_not_in_the_record(tmp_path):
    forecast_files.save([look_of([front(4, [7]), front(4, [9], chance=False)])], tmp_path, after(3))
    # The 12 hours window ends 18 hours after the look, and the 24 hours window 30 hours after it.
    for event in (7, 9):  # A front with no chance has the same windows.
        open_two = forecast_files.of_event(tmp_path, [event], after(17))["fronts"][0]
        open_one = forecast_files.of_event(tmp_path, [event], after(19))["fronts"][0]
        assert "hours_12" in open_two and "hours_24" in open_two
        assert "hours_12" not in open_one and "hours_24" in open_one
        assert forecast_files.of_event(tmp_path, [event], after(31)) is None


def test_the_forecast_is_of_the_newest_look_with_a_front_of_the_event(tmp_path):
    night = after(12)
    forecast_files.save([look_of([front(4, [7]), front(3, [9])])], tmp_path, after(3))
    # The night look has a front of the alert 9, and no front of the alert 7.
    forecast_files.save([look_of([front(5, [9], night)], night)], tmp_path, after(3, night))
    as_of = after(4, night)
    assert forecast_files.of_event(tmp_path, [9], as_of)["look_at"] == text(night)
    assert forecast_files.of_event(tmp_path, [9], as_of)["fronts"][0]["pixels"] == 5
    # The alert 7 keeps the forecast of the look before: its 24 hours window is open.
    older = forecast_files.of_event(tmp_path, [7], as_of)
    assert older["look_at"] == text(LOOK) and set(older["fronts"][0]) >= {"hours_12", "hours_24"}


def test_a_front_with_no_inputs_says_why_it_has_no_chance(tmp_path):
    forecast_files.save([look_of([front(4, [7], chance=False)])], tmp_path, after(3))
    found = forecast_files.of_event(tmp_path, [7], after(4))["fronts"][0]
    assert found["hours_12"]["new_ground"] is None and found["hours_12"]["to"] == text(after(18))
    assert found["no_forecast"] == "no weather before the look"


def test_no_folder_gives_no_forecast(tmp_path):
    assert forecast_files.of_event(tmp_path / "absent", [7], LOOK) is None
    assert forecast_files.is_new(tmp_path / "absent", text(LOOK), 1)
