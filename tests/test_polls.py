"""Tests of the readers of the poll log: the lag of the live data and the read before a pass."""

from datetime import UTC, datetime, timedelta

from chispa import polls


def test_status_counts_the_lag_from_the_newest_pass_with_no_failure(tmp_path, monkeypatch):
    monkeypatch.setattr("chispa.config.LIVE_START", datetime(2026, 11, 20, tzinfo=UTC))
    monkeypatch.setattr("chispa.config.LIVE_POLL_LATE", timedelta(minutes=15))
    folder = tmp_path / "live" / "polls"
    folder.mkdir(parents=True)
    header = "polled_at,source,item,result,new_rows\n"
    good, failed = "2026-11-21T23:55:00+00:00", "2026-11-22T00:05:00+00:00"
    (folder / "2026-11-21.csv").write_text(header + f"{good},firms,VIIRS_NOAA20_NRT,ok,5\n")
    # Ten minutes later each source failed. That pass does not make the data newer.
    (folder / "2026-11-22.csv").write_text(
        header
        + f"{failed},firms,VIIRS_NOAA20_NRT,failed: FIRMS request failed,0\n"
        + f"{failed},goes,request,failed: ConnectionError,0\n"
    )

    def at(text):
        return polls.status(tmp_path, datetime.fromisoformat(text))

    found = at("2026-11-22T00:10:00+00:00")
    assert (found["archive"], found["newest_pass_at"], found["complete_pass_at"]) == (
        False,
        failed,
        good,
    )
    assert found["late_at"] == "2026-11-22T00:10:00+00:00"  # 15 minutes after the good pass
    assert found["sources"] == {
        "firms": {"items": 1, "failed": 1, "new_rows": 0},
        "goes": {"items": 1, "failed": 1, "new_rows": 0},
    }
    # A pass at the as-of time counts. In the live period with no pass, the values are None.
    assert at(good)["complete_pass_at"] == good
    empty = at("2026-11-21T00:00:00+00:00")
    assert (empty["archive"], empty["newest_pass_at"], empty["complete_pass_at"]) == (
        False,
        None,
        None,
    )
    # Before the live logs the store has archive data.
    assert at("2026-11-19T00:00:00+00:00")["archive"] is True


def test_answered_before_gives_the_newest_poll_that_read_the_source(tmp_path, monkeypatch):
    monkeypatch.setattr("chispa.config.LIVE_START", datetime(2026, 11, 21, 18, tzinfo=UTC))
    folder = tmp_path / "live" / "polls"
    folder.mkdir(parents=True)
    header = "polled_at,source,item,result,new_rows\n"
    first, second = "2026-11-21T20:00:00+00:00", "2026-11-21T20:05:00+00:00"
    third, back = "2026-11-21T20:10:00+00:00", "2026-11-23T00:05:00+00:00"
    (folder / "2026-11-21.csv").write_text(
        header
        + f"{first},firms,MODIS_NRT,ok,0\n"
        + f"{second},firms,MODIS_NRT,ok,0\n"
        + f"{second},inpe,request,failed: ConnectionError,0\n"
        + f"{third},firms,MODIS_NRT,failed: FIRMS request failed,0\n"
    )
    (folder / "2026-11-23.csv").write_text(header + f"{back},firms,MODIS_NRT,ok,12\n")

    def before(text, source):
        return polls.answered_before(tmp_path, datetime.fromisoformat(text), source).isoformat()

    # FIRMS failed at 20:10. A failure of INPE at 20:05 does not count for FIRMS.
    assert before(back, "firms") == second
    # INPE failed at 20:05. At 20:10 it had no row: it read nothing new and had no failure.
    assert before(back, "inpe") == third
    # The GOES rows of the poller have the source "noaa". Before the first poll: the live start.
    assert before(back, "noaa") == third
    assert before(first, "firms") == "2026-11-21T18:00:00+00:00"
    # A row has the time of its read, 3 seconds after the start of its pass.
    # That pass does not count.
    assert before("2026-11-23T00:05:03+00:00", "firms") == second
