"""Tests of the tools, with a small store that a person can calculate on paper."""

import inspect
from dataclasses import replace
from datetime import timedelta

import numpy as np
import pytest

from chispa import tools
from chispa.fusion import fuse
from chispa.store import add_detections, open_store, read_detections, replace_fusion
from tests.test_fusion import KM, T0, VIIRS

# VIIRS is at lat -17.5, lon -57.5. It was observed at T0 and was available 3 hours later.
GOES = replace(VIIRS, sensor_family="abi", platform="GOES16", footprint_m=1250.0)
SECOND = replace(
    GOES, observed_at=T0 + timedelta(hours=5), available_at=T0 + timedelta(hours=5, minutes=30)
)
FAR = replace(VIIRS, lat=-19.5, platform="NOAA20")  # 2 degrees to the south: 222 km


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A store with one event of two detections near the position, and one event far away."""
    path = tmp_path / "store.sqlite"
    monkeypatch.setattr("chispa.config.STORE_PATH", path)
    monkeypatch.setattr("chispa.config.RAW_DIR", tmp_path)
    connection = open_store(path)
    add_detections(connection, [VIIRS, SECOND, FAR])
    found = read_detections(connection, T0, T0 + timedelta(days=1))
    replace_fusion(connection, (100, 200), fuse(found, first_id=100))
    return connection


def test_alert_near_has_the_level_of_the_as_of_time(store):
    early = tools.alerts_near(-17.5, -57.5, 10.0, 6.0, as_of=T0 + timedelta(hours=4))
    late = tools.alerts_near(-17.5, -57.5, 10.0, 6.0, as_of=T0 + timedelta(hours=6))
    # At 4 hours only the VIIRS detection was available. At 6 hours GOES was also available.
    assert [(event["level"], event["detections"]) for event in early] == [("LOW", 1)]
    assert [(event["level"], event["detections"]) for event in late] == [("HIGH", 2)]
    assert late[0]["sensor_families"] == ["abi", "viirs"]
    assert late[0]["newest_observation_age_h"] == 1.0  # observed at 5 hours, asked at 6 hours


def test_detection_that_was_not_available_gives_no_alert(store):
    assert tools.alerts_near(-17.5, -57.5, 10.0, 6.0, as_of=T0 + timedelta(hours=2)) == []


def test_alert_far_from_the_position_is_not_in_the_answer(store):
    near = tools.alerts_near(-17.5, -57.5, 10.0, 24.0, as_of=T0 + timedelta(hours=6))
    wide = tools.alerts_near(-17.5, -57.5, 300.0, 24.0, as_of=T0 + timedelta(hours=6))
    assert (len(near), len(wide)) == (1, 2)
    assert [round(event["nearest_km"]) for event in wide] == [0, 222]


def test_event_record_has_the_state_and_the_level_changes_to_the_as_of_time(store, tmp_path):
    event_id = tools.alerts_near(-17.5, -57.5, 10.0, 24.0, as_of=T0 + timedelta(hours=6))[0][
        "event_id"
    ]
    early = tools.event_record(event_id, as_of=T0 + timedelta(hours=4))
    late = tools.event_record(event_id, as_of=T0 + timedelta(hours=6))
    assert [change["level"] for change in early["level_changes"]] == ["LOW"]
    assert [change["level"] for change in late["level_changes"]] == ["LOW", "HIGH"]
    assert (late["level"], late["detections"], late["sensor_families"]) == (
        "HIGH",
        2,
        ["abi", "viirs"],
    )
    assert [found["platform"] for found in late["newest_detections"]] == ["GOES16", "SNPP"]
    assert (late["lat"], late["lon"]) == (-17.5, -57.5)


def test_event_record_says_what_it_cannot_give(store):
    # The test folder has no layers, no masks and no pass list.
    found = tools.event_record(100, as_of=T0 + timedelta(hours=6))
    assert (found["severity"], found["confidence"], found["goes_view"]) == (None, None, None)
    assert found["viirs_passes_after_last_detection"] is None
    assert found["growth"] is None  # one VIIRS pass only
    assert "chispa fetch" in found["notes"][0]


def test_event_record_reads_the_live_mask_of_the_poller(store, tmp_path):
    folder = tmp_path / "live" / "goes_mask"
    (folder / str(T0.year)).mkdir(parents=True)
    # Two pixels: the event is at the first. Scan 1: examined, no fire. Scan 2: cloud.
    np.savez(folder / "grid.npz", lat=np.array([[-17.5, -17.5]]), lon=np.array([[-57.5, -50.0]]))
    times = np.array([(T0 + timedelta(hours=5)).isoformat(), (T0 + timedelta(hours=6)).isoformat()])
    mask = np.array([[[100, 100]], [[200, 100]]], dtype=np.uint8)
    np.savez(folder / str(T0.year) / f"{T0.date()}.npz", times=times, mask=mask)
    at_5 = tools.event_record(100, as_of=T0 + timedelta(hours=5, minutes=30))["goes_view"]
    at_6 = tools.event_record(100, as_of=T0 + timedelta(hours=6))["goes_view"]
    assert (at_5["group"], at_6["group"]) == ("no_fire", "cloud")
    assert at_6["scan_at"] == "2024-08-15T11:00:00+00:00"


def test_two_alerts_are_two_events_before_their_merge_and_one_after(tmp_path, monkeypatch):
    path = tmp_path / "merge.sqlite"
    monkeypatch.setattr("chispa.config.STORE_PATH", path)
    monkeypatch.setattr("chispa.config.RAW_DIR", tmp_path)
    connection = open_store(path)
    north = replace(VIIRS, lat=VIIRS.lat + 2.4 * KM, platform="NOAA20")
    bridge = replace(
        VIIRS,
        lat=VIIRS.lat + 1.2 * KM,
        observed_at=T0 + timedelta(hours=1),
        available_at=VIIRS.available_at + timedelta(hours=1),
    )
    add_detections(connection, [VIIRS, north, bridge])
    found = read_detections(connection, T0, T0 + timedelta(days=1))
    replace_fusion(connection, (100, 200), fuse(found, first_id=100))
    before = VIIRS.available_at + timedelta(minutes=30)
    after = VIIRS.available_at + timedelta(hours=2)
    early = tools.alerts_near(VIIRS.lat, VIIRS.lon, 10.0, 24.0, as_of=before)
    late = tools.alerts_near(VIIRS.lat, VIIRS.lon, 10.0, 24.0, as_of=after)
    assert sorted(event["event_id"] for event in early) == [100, 101]
    assert [(event["event_id"], event["detections"]) for event in late] == [(100, 3)]
    # The newer alert is a part of the older event after the merge.
    assert tools.event_record(101, as_of=after)["event_id"] == 100
    assert tools.event_record(101, as_of=before)["detections"] == 1


def test_each_tool_follows_the_rules_for_a_tool():
    public = [
        function
        for name, function in inspect.getmembers(tools, inspect.isfunction)
        if function.__module__ == tools.__name__ and not name.startswith("_")
    ]
    assert len(public) <= 6
    for function in public:
        signature = inspect.signature(function)
        assert function.__doc__, f"{function.__name__} has no docstring"
        assert signature.return_annotation is not inspect.Signature.empty
        assert all(
            p.annotation is not inspect.Parameter.empty for p in signature.parameters.values()
        )
        # Only the tool that reads the result tables has no as-of time.
        assert "as_of" in signature.parameters or function.__name__ == "evaluation_summary"


def test_bad_argument_is_rejected(store):
    with pytest.raises(ValueError):
        tools.alerts_near(-95.0, -57.5, 10.0, 6.0, as_of=T0)
    with pytest.raises(ValueError):
        tools.alerts_near(-17.5, -57.5, 0.0, 6.0, as_of=T0)
    with pytest.raises(ValueError):
        tools.event_record(100, as_of=T0.replace(tzinfo=None))


def test_evaluation_summary_reads_the_result_tables(tmp_path, monkeypatch):
    monkeypatch.setattr("chispa.config.RESULTS_DIR", tmp_path)
    folder = tmp_path / "2024"
    folder.mkdir()
    for name in ("configurations", "events", "merge_gain"):
        (folder / f"{name}.csv").write_text("fire_recall,config,run_date\n0.5,abc,2026-11-21\n")
    (tmp_path / "SUMMARY.md").write_text("# Results\n\nLimits of these results:\n\n- One limit.\n")
    summary = tools.evaluation_summary(2024)
    assert (summary["configuration"], summary["role"]) == ("abc", "test year of the merge")
    assert summary["configurations"][0]["fire_recall"] == "0.5"
    assert summary["limits"].endswith("- One limit.")
    with pytest.raises(ValueError):
        tools.evaluation_summary(2019)
