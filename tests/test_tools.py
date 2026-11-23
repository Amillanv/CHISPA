"""Tests of the tools, with a small store that a person can calculate on paper."""

from dataclasses import replace
from datetime import timedelta

import pytest

from chispa import tools
from chispa.fusion import fuse
from chispa.store import add_detections, open_store, read_detections, replace_fusion
from tests.test_fusion import T0, VIIRS

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


def test_event_detail_has_the_alert_changes_to_the_as_of_time(store):
    event_id = tools.alerts_near(-17.5, -57.5, 10.0, 24.0, as_of=T0 + timedelta(hours=6))[0][
        "event_id"
    ]
    early = tools.event_detail(event_id, as_of=T0 + timedelta(hours=4))
    late = tools.event_detail(event_id, as_of=T0 + timedelta(hours=6))
    assert [change["level"] for change in early["alert_changes"]] == ["LOW"]
    assert [change["level"] for change in late["alert_changes"]] == ["LOW", "HIGH"]
    assert [found["platform"] for found in late["newest_detections"]] == ["GOES16", "SNPP"]


def test_bad_argument_is_rejected(store):
    with pytest.raises(ValueError):
        tools.alerts_near(-95.0, -57.5, 10.0, 6.0, as_of=T0)
    with pytest.raises(ValueError):
        tools.alerts_near(-17.5, -57.5, 0.0, 6.0, as_of=T0)
    with pytest.raises(ValueError):
        tools.event_detail(100, as_of=T0.replace(tzinfo=None))


def test_evaluation_summary_reads_the_result_tables(tmp_path, monkeypatch):
    monkeypatch.setattr("chispa.config.RESULTS_DIR", tmp_path)
    folder = tmp_path / "2024"
    folder.mkdir()
    for name in ("configurations", "events", "merge_gain"):
        (folder / f"{name}.csv").write_text("fire_recall,config,run_date\n0.5,abc,2026-11-21\n")
    (tmp_path / "SUMMARY.md").write_text("# Results\n\nLimits of these results:\n\n- One limit.\n")
    summary = tools.evaluation_summary(2024)
    assert (summary["configuration"], summary["role"]) == ("abc", "test year")
    assert summary["configurations"][0]["fire_recall"] == "0.5"
    assert summary["limits"].endswith("- One limit.")
    with pytest.raises(ValueError):
        tools.evaluation_summary(2019)
