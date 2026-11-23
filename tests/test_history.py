"""Tests of the history of an event: its passes, their times and its alerts, for paper."""

from datetime import UTC, datetime, timedelta

import numpy as np

from chispa import history

NAN = float("nan")


def found():
    """Seven detections of event 100, in the sequence in which they became available (seconds).

    GOES scan 0 to 600 has two detections: one pass. Its scans of 600 and 1200 are two more passes.
    SNPP has two rows of one pass, one minute apart (FIRMS and INPE). NOAA20 comes 50 minutes later.
    Levels: LOW, then MEDIUM at the second pass, then HIGH at the second sensor family.
    """
    return {
        "family": np.array(["abi", "abi", "abi", "abi", "viirs", "viirs", "viirs"]),
        "platform": np.array(["GOES16"] * 4 + ["SNPP", "SNPP", "NOAA20"]),
        "source": np.array(["noaa"] * 4 + ["firms", "inpe", "firms"]),
        "observed": np.array([300.0, 420.0, 900.0, 1500.0, 0.0, 60.0, 3000.0]),
        "available": np.array([2100.0, 2160.0, 2700.0, 3300.0, 10800.0, 10860.0, 13800.0]),
        "frp_mw": np.array([30.0, 40.0, NAN, 10.0, 5.0, NAN, 2.0]),
        "level": np.array([0, 0, 1, 1, 2, 2, 2]),
        "issued": np.array([100] * 7),
    }


def at(seconds):
    return datetime.fromtimestamp(seconds, UTC).isoformat()


def levels(row):
    return [alert["level"] for alert in row["alerts"]]


def test_passes_follow_the_fusion_and_say_which_pass_raised_the_level(monkeypatch):
    monkeypatch.setattr("chispa.config.TOOL_MAX_PASSES", 60)
    monkeypatch.setattr("chispa.config.LIVE_START", datetime.fromtimestamp(2400, UTC))
    rows, count = history.passes(found(), 100)
    assert count == 5
    summary = [(r["platform"], r["detections"], r["max_frp_mw"], levels(r)) for r in rows]
    assert summary == [
        ("GOES16", 2, 40.0, ["LOW"]),
        ("GOES16", 1, None, ["MEDIUM"]),
        ("GOES16", 1, 10.0, []),
        ("SNPP", 2, 5.0, ["HIGH"]),
        ("NOAA20", 1, 2.0, []),
    ]
    # A pass has its first observation and the first time that CHISPA had it.
    assert (rows[0]["observed_at"], rows[0]["available_at"]) == (at(300), at(2100))
    # Before the live logs the time of availability is an estimate. NOAA20 is after their start.
    assert [r["estimated"] for r in rows] == [True, True, True, True, False]


def test_record_shows_the_newest_passes_and_each_pass_that_raised_the_level(monkeypatch):
    monkeypatch.setattr("chispa.config.TOOL_MAX_PASSES", 1)
    rows, count = history.passes(found(), 100)
    # The newest pass is NOAA20. The GOES scan of 1200 raised nothing: it is not shown.
    assert count == 5
    assert [levels(r) for r in rows] == [["LOW"], ["MEDIUM"], ["HIGH"], []]
    assert rows[-1]["platform"] == "NOAA20"


def test_one_pass_can_raise_the_level_two_times_and_each_level_has_its_time():
    # TERRA, one pass of two detections: the first has a nominal confidence (LOW). The second has
    # a high confidence (MEDIUM): its INPE row came in a later poll. NOAA20 adds a family (HIGH).
    passes = {
        "family": np.array(["modis", "modis", "viirs"]),
        "platform": np.array(["TERRA", "TERRA", "NOAA20"]),
        "source": np.array(["firms", "inpe", "firms"]),
        "observed": np.array([0.0, 0.0, 3600.0]),
        "available": np.array([7200.0, 9900.0, 10200.0]),
        "frp_mw": np.array([80.0, NAN, 30.0]),
        "level": np.array([0, 1, 2]),
        "issued": np.array([100] * 3),
    }
    rows, count = history.passes(passes, 100)
    assert count == 2
    assert [(r["platform"], r["source"], r["alerts"]) for r in rows] == [
        ("TERRA", "firms", [{"level": "LOW", "at": at(7200)}, {"level": "MEDIUM", "at": at(9900)}]),
        ("NOAA20", "firms", [{"level": "HIGH", "at": at(10200)}]),
    ]


def test_stop_counts_only_the_part_of_the_time_to_chispa_with_no_poll(tmp_path, monkeypatch):
    monkeypatch.setattr("chispa.config.LIVE_POLL_LATE", timedelta(minutes=15))
    folder = tmp_path / "live" / "polls"
    folder.mkdir(parents=True)
    # Two complete polls, at 10:00 and at 12:00 UTC. The poller stopped between them.
    (folder / "2026-11-23.csv").write_text(
        "polled_at,source,item,result,new_rows\n"
        "2026-11-23T10:00:00+00:00,firms,MODIS_NRT,ok,0\n"
        "2026-11-23T12:00:00+00:00,firms,MODIS_NRT,ok,1\n"
    )

    def row(observed):
        return {
            "observed_at": f"2026-11-23T{observed}:00+00:00",
            "available_at": "2026-11-23T12:00:00+00:00",
            "source": "firms",
            "estimated": False,
        }

    rows = history.with_stops([row("11:59"), row("08:00"), row("11:00")], tmp_path)
    # Observed one minute before the poll: the stop added one minute at most. That is not late.
    # Observed before the stop: the stop added two hours at most. Observed in it: one hour.
    assert [r["poller_stop_h"] for r in rows] == [None, 2.0, 1.0]
