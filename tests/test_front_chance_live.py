"""Tests of the live chance of a front, with cases small enough for paper."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from chispa import forecast_files, front_chance, risk_files, tools
from chispa.fusion import fuse
from chispa.store import add_detections, open_store, read_detections, replace_fusion, to_text
from tests.test_fusion import T0, VIIRS

# The first detection of the alert: a GOES scan of T0, which CHISPA had 20 minutes later.
AVAILABLE = T0 + timedelta(minutes=20)
GOES = replace(VIIRS, sensor_family="abi", platform="GOES19", available_at=AVAILABLE)
# The model has one input. With 2 detections the input is ln(3): the odds are 3 to 1.
MODEL = {"inputs": ["detections_log"], "mean": [0.0], "spread": [1.0], "start": 0.0}
SAVED = {"mark": "the mark", "model": MODEL | {"weights": [1.0]}}
ONLY_GOES = {"families": 1.0, "has_abi": 1.0, "detections_log": float(np.log(3))}
# The first detection of the alert, as the name of its files has it.
FIRST = (int(AVAILABLE.timestamp()), int(T0.timestamp()), GOES.lat, GOES.lon)


def risk_of(first: datetime, values: dict | None, moment: str = "0") -> dict:
    """The file of the growth risk of an alert whose first detection CHISPA had at a time."""
    one = {"alert": 100, "moment_h": moment, "first_available_at": to_text(first)}
    one |= {"moment_at": to_text(first + timedelta(minutes=30)), "first_observed_at": to_text(T0)}
    one |= {"first_lat": GOES.lat, "first_lon": GOES.lon}
    if values is None:
        return one | {"no_answer": "the first detection is not in the Pantanal biome of Brazil"}
    place = {"lat": GOES.lat, "lon": GOES.lon, "detections": 2, "weather_open_meteo_days": 0}
    return one | place | {"inputs": values, "limits": []}


def save_chance(folder, made: datetime) -> None:
    """Save the chance of the alert as a file that was complete at a time."""
    risk = risk_of(AVAILABLE, ONLY_GOES) | {"made_at": to_text(made)}
    chance = front_chance.answer(risk, SAVED, made)
    risk_files.write_new(risk_files.path_of(folder, "0", FIRST), chance)


@pytest.fixture(autouse=True)
def settings(monkeypatch, tmp_path):
    monkeypatch.setattr("chispa.config.SEVERITY_EVAL_HOURS", 24.0)
    monkeypatch.setattr("chispa.config.PASS_GAP", timedelta(minutes=30))
    monkeypatch.setattr("chispa.config.RISK_LIVE_DIR", tmp_path / "risks")
    monkeypatch.setattr("chispa.config.FRONT_CHANCE_LIVE_DIR", tmp_path / "front_chances")
    monkeypatch.setattr("chispa.config.FRONT_CHANCE_MODEL_PATH", tmp_path / "model.json")
    monkeypatch.setattr("chispa.config.FORECAST_LIVE_DIR", tmp_path / "forecasts")


def test_only_an_alert_with_goes_detections_gets_a_chance():
    at = AVAILABLE + timedelta(minutes=31)
    risk = risk_of(AVAILABLE, ONLY_GOES) | {"made_at": to_text(at)}
    made = front_chance.answer(risk, SAVED, at)
    # Odds of 3 to 1 are a chance of 0.75. The chance is for a front in the 24 hours.
    assert (made["chance"], made["model"]) == (0.75, "the mark")
    assert made["until"] == to_text(AVAILABLE + timedelta(hours=24))
    assert (made["made_at"], made["inputs_made_at"]) == (to_text(at), risk["made_at"])
    # An alert with a GOES detection and a VIIRS detection has two sensor families.
    both = ONLY_GOES | {"families": 2.0}
    assert front_chance.answer(risk | {"inputs": both}, SAVED, at) is None
    # An alert with one family that is not GOES.
    viirs = ONLY_GOES | {"has_abi": 0.0}
    assert front_chance.answer(risk | {"inputs": viirs}, SAVED, at) is None
    # An alert with no answer of the growth risk has no inputs.
    assert front_chance.answer(risk_of(AVAILABLE, None), SAVED, at) is None


def test_a_chance_from_the_second_moment_or_later_is_not_made():
    risk = risk_of(AVAILABLE, ONLY_GOES) | {"made_at": to_text(AVAILABLE + timedelta(minutes=31))}
    # An update can find the alert one second before its second moment, and make the file later.
    until = AVAILABLE + timedelta(hours=24)
    assert front_chance.answer(risk, SAVED, until - timedelta(seconds=1))["chance"] == 0.75
    assert front_chance.answer(risk, SAVED, until) is None


def test_an_alert_is_due_before_its_second_moment_and_with_no_file(tmp_path):
    risks, folder = tmp_path / "risks", tmp_path / "front_chances"
    now = AVAILABLE + timedelta(hours=1)
    new = risk_files.save(risk_of(AVAILABLE, ONLY_GOES), risks, now)
    # The second moment of an alert of 25 hours before now is in the past: the answer is known.
    risk_files.save(risk_of(now - timedelta(hours=25), ONLY_GOES), risks, now)
    # The file of the second moment of the growth risk is not read.
    risk_files.save(risk_of(AVAILABLE, ONLY_GOES, moment="24"), risks, now)
    assert front_chance.due(risks, folder, now) == [new]
    assert front_chance.due(risks, folder, AVAILABLE + timedelta(hours=24)) == []
    # Before the first moment of the alert, 30 minutes after its first detection, it is not due.
    assert front_chance.due(risks, folder, AVAILABLE + timedelta(minutes=29)) == []
    assert front_chance.due(risks, folder, AVAILABLE + timedelta(minutes=30)) == [new]
    # The file of the chance has the name of the file of the growth risk, in its own folder.
    assert front_chance.path_of(folder, new) == risk_files.path_of(folder, "0", FIRST)
    save_chance(folder, now)
    assert front_chance.due(risks, folder, now) == []


def test_an_alert_of_december_is_due_in_january(tmp_path):
    risks, first = tmp_path / "risks", datetime(2024, 12, 31, 23, 30, tzinfo=UTC)
    new = risk_files.save(risk_of(first, ONLY_GOES), risks, first + timedelta(minutes=31))
    now = datetime(2025, 1, 1, 0, 10, tzinfo=UTC)
    assert front_chance.due(risks, tmp_path / "front_chances", now) == [new]


def test_update_makes_one_file_for_each_chance_and_does_not_change_it(tmp_path, monkeypatch):
    now = AVAILABLE + timedelta(hours=1)
    assert "Run `chispa forecast --front-chance`" in front_chance.update(now)
    risk_files.save_models(SAVED, tmp_path / "model.json")
    risk_files.save(risk_of(AVAILABLE, ONLY_GOES), tmp_path / "risks", now)
    # A second alert of the same poll, at a different place, with a VIIRS detection.
    other = risk_of(AVAILABLE, ONLY_GOES | {"families": 2.0}) | {"first_lat": -18.5}
    risk_files.save(other, tmp_path / "risks", now)
    assert front_chance.update(now) == "front chance: 1 new files."
    (path,) = (tmp_path / "front_chances" / "2024").glob("*.json")
    first = json.loads(path.read_text())
    assert (first["chance"], first["alert"], first["moment_h"]) == (0.75, 100, "0")
    assert front_chance.update(now + timedelta(hours=1)) == "front chance: 0 new files."
    assert json.loads(path.read_text()) == first
    # A model of other settings is not the model of now.
    monkeypatch.setattr(risk_files, "config_hash", lambda: "other settings")
    assert "no saved model of now" in front_chance.update(now)


def test_the_file_of_a_chance_gets_its_name_from_the_file_of_the_growth_risk(tmp_path):
    now = AVAILABLE + timedelta(hours=1)
    risk_files.save_models(SAVED, tmp_path / "model.json")
    path = risk_files.save(risk_of(AVAILABLE, ONLY_GOES), tmp_path / "risks", now)
    # A file of the growth risk from before 2026-11-28 has the first detection of its alert only
    # in its name: the observation time and the place are not in the file.
    absent = ("first_observed_at", "first_lat", "first_lon")
    risk = json.loads(path.read_text())
    path.write_text(json.dumps({key: value for key, value in risk.items() if key not in absent}))
    assert front_chance.update(now) == "front chance: 1 new files."
    # The record finds the file of the chance by the first detection of the alert.
    assert risk_files.path_of(tmp_path / "front_chances", "0", FIRST).exists()


def found_of(family: list[str], source: list[str]) -> dict:
    """The detections of the event of alert 100. The first is the GOES detection of the alert."""
    seconds = int(AVAILABLE.timestamp())
    count = len(family)
    found = {"issued": np.full(count, 100), "available": seconds + 3600 * np.arange(count)}
    found |= {"observed": np.full(count, int(T0.timestamp()))}
    found |= {"lat": np.full(count, GOES.lat), "lon": np.full(count, GOES.lon)}
    return found | {"family": np.array(family), "source": np.array(source)}


def test_record_has_the_chance_from_its_file_to_its_end(tmp_path):
    made = AVAILABLE + timedelta(minutes=31)
    save_chance(tmp_path, made)
    found = found_of(["abi"], ["firms"])
    assert front_chance.of_event(tmp_path, found, 100, made - timedelta(minutes=1)) is None
    shown = front_chance.of_event(tmp_path, found, 100, made)
    assert shown == {
        "front_chance": {
            "chance": 0.75,
            "until": to_text(AVAILABLE + timedelta(hours=24)),
            "moment_at": to_text(AVAILABLE + timedelta(minutes=30)),
            "made_at": to_text(made),
            "model": "the mark",
            "weather_open_meteo_days": 0,
        }
    }
    last = AVAILABLE + timedelta(hours=23, minutes=59)
    assert front_chance.of_event(tmp_path, found, 100, last) == shown
    assert front_chance.of_event(tmp_path, found, 100, AVAILABLE + timedelta(hours=24)) is None
    # The event of a different alert does not have this chance.
    assert front_chance.of_event(tmp_path, found, 101, made) is None


def test_record_has_no_chance_when_the_event_has_a_viirs_pixel_of_firms(tmp_path):
    made = AVAILABLE + timedelta(minutes=31)
    save_chance(tmp_path, made)
    later = AVAILABLE + timedelta(hours=2)
    # A VIIRS row of INPE is not a front: a front is a VIIRS pixel of FIRMS.
    inpe = found_of(["abi", "viirs"], ["firms", "inpe"])
    assert front_chance.of_event(tmp_path, inpe, 100, later) is not None
    firms = found_of(["abi", "viirs"], ["firms", "firms"])
    assert front_chance.of_event(tmp_path, firms, 100, later) is None


def test_event_record_has_the_chance_until_viirs_sees_the_event(tmp_path, monkeypatch):
    monkeypatch.setattr("chispa.config.STORE_PATH", tmp_path / "store.sqlite")
    monkeypatch.setattr("chispa.config.RAW_DIR", tmp_path)
    connection = open_store(tmp_path / "store.sqlite")
    # The GOES detection starts alert 100. CHISPA has a VIIRS pixel at its place at 3 hours.
    add_detections(connection, [GOES, VIIRS])
    found = read_detections(connection, T0, T0 + timedelta(days=1))
    replace_fusion(connection, (100, 200), fuse(found, first_id=100))
    save_chance(tmp_path / "front_chances", AVAILABLE + timedelta(minutes=31))
    assert tools.event_record(100, as_of=AVAILABLE + timedelta(minutes=30))["forecast"] is None
    early = tools.event_record(100, as_of=T0 + timedelta(hours=2))
    assert early["forecast"]["front_chance"]["chance"] == 0.75
    # At 3 hours the event has a VIIRS pixel, and no forecast file yet: the chance has its answer.
    assert tools.event_record(100, as_of=T0 + timedelta(hours=3))["forecast"] is None
    # The forecast of the front of that pixel is the field from the time of its file.
    look, at = T0, T0 + timedelta(hours=4)
    window = {"from": (look + timedelta(hours=6)).isoformat(), "new_ground": 0.3}
    window |= {"to": (look + timedelta(hours=18)).isoformat(), "sectors": {"north": 0.1}}
    front = {"lat": -17.5, "lon": -57.5, "pixels": 4, "events": [100], "hours_12": window}
    saved = {"look_at": look.isoformat(), "large_growth_pixels": 10, "fronts": [front]}
    forecast_files.save([saved], tmp_path / "forecasts", at)
    late = tools.event_record(100, as_of=at)["forecast"]
    assert "front_chance" not in late and len(late["fronts"]) == 1
