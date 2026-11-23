"""Tests of the history of an event: its passes, their times and its alerts, for paper."""

from datetime import UTC, datetime

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
        "observed": np.array([300.0, 420.0, 900.0, 1500.0, 0.0, 60.0, 3000.0]),
        "available": np.array([2100.0, 2160.0, 2700.0, 3300.0, 10800.0, 10860.0, 13800.0]),
        "frp_mw": np.array([30.0, 40.0, NAN, 10.0, 5.0, NAN, 2.0]),
        "level": np.array([0, 0, 1, 1, 2, 2, 2]),
        "issued": np.array([100] * 7),
    }


def at(seconds):
    return datetime.fromtimestamp(seconds, UTC).isoformat()


def test_passes_follow_the_fusion_and_say_which_pass_raised_the_level(monkeypatch):
    monkeypatch.setattr("chispa.config.TOOL_MAX_PASSES", 60)
    monkeypatch.setattr("chispa.config.LIVE_START", datetime.fromtimestamp(2400, UTC))
    rows, count = history.passes(found(), 100)
    assert count == 5
    summary = [(r["platform"], r["detections"], r["max_frp_mw"], r["alert"]) for r in rows]
    assert summary == [
        ("GOES16", 2, 40.0, "LOW"),
        ("GOES16", 1, None, "MEDIUM"),
        ("GOES16", 1, 10.0, None),
        ("SNPP", 2, 5.0, "HIGH"),
        ("NOAA20", 1, 2.0, None),
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
    assert [r["alert"] for r in rows] == ["LOW", "MEDIUM", "HIGH", None]
    assert rows[-1]["platform"] == "NOAA20"
