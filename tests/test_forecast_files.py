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
    monkeypatch.setattr("chispa.config.FRONT_LARGE_PIXELS", 10)


def text(time: datetime) -> str:
    return time.isoformat(timespec="minutes")


def front(pixels: int, events: list[int], look_at: datetime = LOOK) -> dict:
    """A front with the two windows of its look, and a chance for each of the two sectors."""
    found = {"lat": -17.35, "lon": -57.24, "pixels": pixels, "events": events}
    for hours, high in ((12, 18), (24, 30)):
        limits = (look_at + timedelta(hours=6), look_at + timedelta(hours=high))
        found[f"hours_{hours}"] = {"from": text(limits[0]), "to": text(limits[1])}
        found[f"hours_{hours}"] |= {"new_ground": 0.2, "large_growth": 0.05}
        found[f"hours_{hours}"]["sectors"] = {"north": 0.1, "east": 0.02}
    return found


def look_of(fronts: list[dict], made_h: float, look_at: datetime = LOOK) -> dict:
    """The forecast of a look, made some hours after the look."""
    made_at = text(look_at + timedelta(hours=made_h))
    return {"look_at": text(look_at), "made_at": made_at, "fronts": fronts}


def test_the_first_forecast_of_a_look_stays_when_a_newer_one_comes(tmp_path):
    first = forecast_files.save([look_of([front(9, [7])], 3)], tmp_path)
    assert [path.name for path in first] == ["2026-11-25T1719_2026-11-25T2019.json"]
    # The same look again with the same pixels: no new file.
    assert forecast_files.save([look_of([front(9, [7])], 3.1)], tmp_path) == []
    assert not forecast_files.is_new(tmp_path, text(LOOK), 9)
    # A second satellite gave more pixels: a new file, and the first file stays as it was.
    assert forecast_files.is_new(tmp_path, text(LOOK), 12)
    second = forecast_files.save([look_of([front(12, [7])], 4)], tmp_path)
    assert [path.name for path in second] == ["2026-11-25T1719_2026-11-25T2119.json"]
    assert json.loads(first[0].read_text())["fronts"][0]["pixels"] == 9
    assert forecast_files.save([look_of([front(12, [7])], 4.1)], tmp_path) == []


def test_an_event_gets_the_fronts_with_one_of_its_issued_ids(tmp_path):
    # The look has a front of 4 pixels of the alert 7, and a front of 1 pixel of the alert 9.
    forecast_files.save([look_of([front(4, [7]), front(1, [9])], 3)], tmp_path)
    as_of = LOOK + timedelta(hours=4)
    found = forecast_files.of_event(tmp_path, [7], as_of)
    assert (found["look_at"], found["made_at"]) == (text(LOOK), text(LOOK + timedelta(hours=3)))
    assert found["large_growth_pixels"] == 10 and len(found["fronts"]) == 1
    assert found["fronts"][0]["pixels"] == 4 and "events" not in found["fronts"][0]
    assert found["fronts"][0]["hours_12"]["sectors"] == {"north": 0.1, "east": 0.02}
    # The alert 8 merged into an event that also has the alert 7: the event has the front.
    assert forecast_files.of_event(tmp_path, [8, 7], as_of)["fronts"][0]["pixels"] == 4
    assert forecast_files.of_event(tmp_path, [5], as_of) is None


def test_a_small_front_has_its_chance_and_no_sectors(tmp_path):
    forecast_files.save([look_of([front(4, [7]), front(1, [9])], 3)], tmp_path)
    small = forecast_files.of_event(tmp_path, [9], LOOK + timedelta(hours=4))["fronts"][0]
    assert small["hours_12"]["new_ground"] == 0.2 and small["hours_12"]["sectors"] is None
    assert small["hours_24"]["sectors"] is None


def test_the_record_has_only_what_existed_at_its_time(tmp_path):
    forecast_files.save([look_of([front(4, [7])], 3)], tmp_path)
    forecast_files.save([look_of([front(6, [7])], 5)], tmp_path)
    # At 2 hours after the look no file exists. At 4 hours the first file. At 6 hours the second.
    assert forecast_files.of_event(tmp_path, [7], LOOK + timedelta(hours=2)) is None
    assert (
        forecast_files.of_event(tmp_path, [7], LOOK + timedelta(hours=4))["fronts"][0]["pixels"]
        == 4
    )
    assert (
        forecast_files.of_event(tmp_path, [7], LOOK + timedelta(hours=6))["fronts"][0]["pixels"]
        == 6
    )


def test_a_window_that_ended_is_not_in_the_record(tmp_path):
    forecast_files.save([look_of([front(4, [7])], 3)], tmp_path)
    # The 12 hours window ends 18 hours after the look, and the 24 hours window 30 hours after it.
    open_two = forecast_files.of_event(tmp_path, [7], LOOK + timedelta(hours=17))["fronts"][0]
    open_one = forecast_files.of_event(tmp_path, [7], LOOK + timedelta(hours=19))["fronts"][0]
    assert "hours_12" in open_two and "hours_24" in open_two
    assert "hours_12" not in open_one and open_one["hours_24"]["new_ground"] == 0.2
    assert forecast_files.of_event(tmp_path, [7], LOOK + timedelta(hours=31)) is None


def test_the_forecast_is_of_the_newest_look_with_a_front_of_the_event(tmp_path):
    night = LOOK + timedelta(hours=12)
    forecast_files.save([look_of([front(4, [7]), front(3, [9])], 3)], tmp_path)
    # The night look has a front of the alert 9, and no front of the alert 7.
    forecast_files.save([look_of([front(5, [9], night)], 3, night)], tmp_path)
    as_of = night + timedelta(hours=4)
    assert forecast_files.of_event(tmp_path, [9], as_of)["look_at"] == text(night)
    assert forecast_files.of_event(tmp_path, [9], as_of)["fronts"][0]["pixels"] == 5
    # The alert 7 keeps the forecast of the look before: its 24 hours window is open.
    older = forecast_files.of_event(tmp_path, [7], as_of)
    assert older["look_at"] == text(LOOK) and set(older["fronts"][0]) >= {"hours_12", "hours_24"}


def test_a_front_with_no_inputs_says_why_it_has_no_chance(tmp_path):
    bare = {"lat": -17.35, "lon": -57.24, "pixels": 4, "events": [7]}
    bare |= {"hours_12": None, "hours_24": None, "no_forecast": "no weather before the look"}
    forecast_files.save([look_of([bare], 3)], tmp_path)
    found = forecast_files.of_event(tmp_path, [7], LOOK + timedelta(hours=4))["fronts"][0]
    assert found["hours_12"] is None and found["no_forecast"] == "no weather before the look"


def test_no_folder_gives_no_forecast(tmp_path):
    assert forecast_files.of_event(tmp_path / "absent", [7], LOOK) is None
    assert forecast_files.is_new(tmp_path / "absent", text(LOOK), 1)
