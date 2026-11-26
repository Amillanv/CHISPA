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
    # The first detection was at T0. At 6 hours the fire is 6 hours old or older.
    assert (early["hours_from_first_detection"], late["hours_from_first_detection"]) == (4.0, 6.0)
    day = {"day": "2024-08-15", "detections": 2, "sensor_families": ["abi", "viirs"]}
    assert late["timeline"] == [day]


def test_event_record_says_what_it_cannot_give(store):
    # The test folder has no layers, no masks and no pass list.
    found = tools.event_record(100, as_of=T0 + timedelta(hours=6))
    assert (found["severity"], found["confidence"], found["goes_view"]) == (None, None, None)
    assert found["viirs_passes_after_last_detection"] is None
    assert (found["growth"], found["growth_steps"]) == (None, [])  # one VIIRS pass only
    assert "chispa fetch" in found["notes"][0]


def test_event_record_reads_a_live_mask_only_after_the_poller_got_it(store, tmp_path):
    folder = tmp_path / "live" / "goes_mask"
    (folder / str(T0.year)).mkdir(parents=True)
    # Two pixels: the event is at the first. The newest detection is the GOES scan of 5 hours.
    # Scans at the event: 5 hours no fire, 6 hours cloud, 7 hours no fire.
    np.savez(folder / "grid.npz", lat=np.array([[-17.5, -17.5]]), lon=np.array([[-57.5, -50.0]]))
    scans = [T0 + timedelta(hours=5), T0 + timedelta(hours=6), T0 + timedelta(hours=7)]
    times = np.array([scan.isoformat() for scan in scans])
    seen = np.array([(scan + timedelta(minutes=12)).isoformat() for scan in scans])
    mask = np.array([[[100, 100]], [[200, 100]], [[100, 200]]], dtype=np.uint8)
    np.savez(folder / str(T0.year) / f"{T0.date()}.npz", times=times, seen=seen, mask=mask)

    def view_at(**after):
        return tools.event_record(100, as_of=T0 + timedelta(**after))["goes_view"]

    # At 6 hours and 5 minutes the poller did not have the scan of 6 hours.
    # The scan of 5 hours is the newest detection itself: it is not after it.
    early = view_at(hours=6, minutes=5)
    assert (early["group"], early["after_last_detection"]) == ("no_fire", {})
    # With no scan after the detection, the last clear look is the detection.
    assert early["last_clear_look"] == {
        "at": "2024-08-15T10:00:00+00:00",
        "answer": "fire",
        "kind": "last_detection",
        "scans_after": 0,
        "groups_after": {},
    }
    assert view_at(hours=6, minutes=12) == {
        "scan_at": "2024-08-15T11:00:00+00:00",
        "group": "cloud",
        "pixels": 1,
        "scans_after_last_detection": 1,
        "after_last_detection": {"cloud": 1},
        "runs_after_last_detection": [
            {
                "from": "2024-08-15T11:00:00+00:00",
                "to": "2024-08-15T11:00:00+00:00",
                "answer": "not_seen",
                "scans": 1,
                "groups": {"cloud": 1},
            }
        ],
        "last_clear_look": {
            "at": "2024-08-15T10:00:00+00:00",
            "answer": "fire",
            "kind": "last_detection",
            "scans_after": 1,
            "groups_after": {"cloud": 1},
        },
    }
    # The scan of 7 hours examined the place and found no fire: the last clear look.
    late = view_at(hours=7, minutes=12)
    assert late["after_last_detection"] == {"cloud": 1, "no_fire": 1}
    assert late["last_clear_look"]["at"] == "2024-08-15T12:00:00+00:00"
    # The day after, with no scan of that day, the record gives the last scan of the day before.
    assert view_at(days=1, hours=1)["group"] == "no_fire"
    # Two days after, the newest saved scan is older than the day before: it is not a view of now.
    assert view_at(days=2, hours=1) is None


def test_level_changes_are_the_history_of_the_event_itself(tmp_path, monkeypatch):
    path = tmp_path / "levels.sqlite"
    monkeypatch.setattr("chispa.config.STORE_PATH", path)
    monkeypatch.setattr("chispa.config.RAW_DIR", tmp_path)
    connection = open_store(path)
    north = VIIRS.lat + 2.4 * KM
    start = VIIRS.available_at
    # Alert 100: one VIIRS detection, LOW. Alert 101 at the north: VIIRS then MODIS, HIGH.
    second = replace(VIIRS, lat=north, platform="NOAA20", available_at=start + timedelta(minutes=1))
    third = replace(second, sensor_family="modis", platform="TERRA")
    third = replace(third, available_at=start + timedelta(minutes=2))
    # One hour later a detection between the two merges alert 101 into alert 100.
    bridge = replace(VIIRS, lat=VIIRS.lat + 1.2 * KM, observed_at=T0 + timedelta(hours=1))
    bridge = replace(bridge, available_at=start + timedelta(hours=1))
    add_detections(connection, [VIIRS, second, third, bridge])
    found = read_detections(connection, T0, T0 + timedelta(days=1))
    replace_fusion(connection, (100, 200), fuse(found, first_id=100))
    record = tools.event_record(100, as_of=start + timedelta(hours=2))
    changes = [(change["level"], change["at"]) for change in record["level_changes"]]
    assert (record["detections"], record["level"]) == (4, "HIGH")
    # The absorbed alert was HIGH after two minutes. This event was HIGH only at the merge.
    high_at = (start + timedelta(hours=1)).isoformat()
    assert changes == [("LOW", start.isoformat()), ("HIGH", high_at)]


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
    merged = {"at": bridge.available_at.isoformat(), "alert_id": 101, "into_id": 100}
    assert tools.event_record(101, as_of=after)["absorbed"] == [merged]
    assert tools.event_record(100, as_of=before)["absorbed"] == []
    assert tools.event_record(101, as_of=before)["detections"] == 1
    # The activity counts the events of the as-of time: two alerts before the merge, one after.
    # After the merge the event has passes of two VIIRS satellites, thus it is MEDIUM.
    early_step = tools.activity(3.0, 3.0, as_of=before)["steps"][0]["events"]
    late_step = tools.activity(3.0, 3.0, as_of=after)["steps"][0]["events"]
    assert early_step == {"LOW": 2, "MEDIUM": 0, "HIGH": 0}
    assert late_step == {"LOW": 0, "MEDIUM": 1, "HIGH": 0}


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


def test_activity_counts_each_event_in_the_step_of_its_detection(store):
    # Steps of 3 hours to 6 hours. VIIRS and FAR became available at 3 hours: the end of step 1.
    # GOES became available at 5 hours 30 minutes, in step 2, and made the event HIGH.
    found = tools.activity(6.0, 3.0, as_of=T0 + timedelta(hours=6))
    first, second = found["steps"]
    assert (first["start"], first["end"]) == (T0.isoformat(), (T0 + timedelta(hours=3)).isoformat())
    assert first["events"] == {"LOW": 2, "MEDIUM": 0, "HIGH": 0}
    assert second["events"] == {"LOW": 0, "MEDIUM": 0, "HIGH": 1}
    assert (first["detections"], second["detections"]) == ({"viirs": 2}, {"abi": 1})
    newest = (T0.isoformat(), (T0 + timedelta(hours=5)).isoformat())
    assert (found["newest_observed_at"]["viirs"], found["newest_observed_at"]["abi"]) == newest


def test_bad_argument_is_rejected(store):
    with pytest.raises(ValueError):
        tools.alerts_near(-95.0, -57.5, 10.0, 6.0, as_of=T0)
    with pytest.raises(ValueError):
        tools.alerts_near(-17.5, -57.5, 0.0, 6.0, as_of=T0)
    with pytest.raises(ValueError):
        tools.event_record(100, as_of=T0.replace(tzinfo=None))
    with pytest.raises(ValueError):
        tools.activity(7.0, 3.0, as_of=T0)  # not a multiple of the step
    with pytest.raises(ValueError):
        tools.activity(0.004, 0.0004, as_of=T0)  # steps of 1.44 seconds


def test_evaluation_summary_reads_the_result_tables(tmp_path, monkeypatch):
    monkeypatch.setattr("chispa.config.RESULTS_DIR", tmp_path)
    folder = tmp_path / "2024"
    folder.mkdir()
    for name in ("configurations", "events", "merge_gain"):
        (folder / f"{name}.csv").write_text("fire_recall\n0.5\n")
    # The stamp of each table of the year is in one file, not in the rows of a table.
    (folder / "stamps.csv").write_text("table,config,run_date\nconfigurations,abc,2026-11-21\n")
    (tmp_path / "SUMMARY.md").write_text("# Results\n\nLimits of these results:\n\n- One limit.\n")
    summary = tools.evaluation_summary(2024)
    assert (summary["configuration"], summary["role"]) == ("abc", "test year of the merge")
    assert summary["run_date"] == "2026-11-21"
    assert summary["configurations"] == [{"fire_recall": "0.5"}]
    assert summary["limits"].endswith("- One limit.")
    with pytest.raises(ValueError):
        tools.evaluation_summary(2019)
