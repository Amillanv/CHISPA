"""Tests of the store build."""

import csv
import shutil
from pathlib import Path

from chispa import config
from chispa.build import read_raw
from chispa.store import add_detections, open_store

SAMPLES = Path(__file__).parent / "samples"


def make_raw(raw_dir: Path) -> None:
    for product in ("VIIRS_SNPP_SP", "MODIS_SP", "GOES_NRT"):
        (raw_dir / "firms" / product).mkdir(parents=True)
        shutil.copy(SAMPLES / f"firms_{product}.csv", raw_dir / "firms" / product / "sample.csv")
    (raw_dir / "inpe").mkdir()
    shutil.copy(SAMPLES / "inpe_202302.csv", raw_dir / "inpe" / "focos_mensal_br_202302.csv")
    (raw_dir / "goes").mkdir()
    (raw_dir / "goes" / "2024-10-01.csv").write_text(
        "observed_at,lat,lon,mask,frp_mw\n2024-10-01T15:00:00+00:00,-17.5,-57.5,30,20.7\n"
    )


def test_build_reads_each_source(tmp_path):
    make_raw(tmp_path / "raw")
    store = open_store(tmp_path / "store.sqlite")
    totals = dict.fromkeys(("firms", "noaa", "inpe"), 0)
    for source, detections, rejected in read_raw(tmp_path / "raw"):
        totals[source] += add_detections(store, detections) + rejected
    # The samples hold 4 + 4 + 4 FIRMS rows that we use.
    assert totals == {"firms": 12, "noaa": 1, "inpe": 10}


def test_live_row_has_the_time_of_the_first_view_or_an_estimate_after_a_stop(tmp_path, monkeypatch):
    from datetime import UTC, datetime, timedelta

    from chispa.build import read_live

    monkeypatch.setattr("chispa.config.LIVE_POLL_LATE", timedelta(minutes=15))
    monkeypatch.setattr("chispa.config.LIVE_NORMAL_WAIT", timedelta(minutes=3))

    live = tmp_path / "raw" / "live"
    (live / "goes").mkdir(parents=True)
    (live / "goes" / "2026-11-21.csv").write_text(
        "observed_at,lat,lon,mask,frp_mw,first_seen_at,published_at\n"
        "2026-11-21T19:00:00+00:00,-17.5,-57.5,10,20.7,"
        "2026-11-21T19:15:00+00:00,2026-11-21T19:10:10+00:00\n"
    )
    (live / "inpe").mkdir()
    (live / "inpe" / "2026-11-21.csv").write_text(
        "lat,lon,satelite,data,first_seen_at,published_at\n"
        " -17.25, -58.36,NOAA-21,2026-11-21 16:56:00,"
        "2026-11-21T20:48:58+00:00,2026-11-21T20:20:02+00:00\n"
    )
    found = {source: detections[0] for source, detections, _ in read_live(tmp_path / "raw")}
    assert (found["noaa"].platform, found["inpe"].platform) == ("GOES19", "NOAA21")
    # The poller saw the GOES scan 5 minutes after its publication: the time is a measurement.
    assert found["noaa"].available_at == datetime(2026, 11, 21, 19, 15, tzinfo=UTC)
    assert found["noaa"].available_estimated is False
    # It saw the INPE file 29 minutes after its publication: a stop. Publication plus 3 minutes.
    assert found["inpe"].available_at == datetime(2026, 11, 21, 20, 23, 2, tzinfo=UTC)
    assert found["inpe"].available_estimated is True


def test_firms_row_that_a_pass_saw_after_a_stop_gets_an_estimate(tmp_path, monkeypatch):
    from datetime import UTC, datetime, timedelta

    from chispa.build import read_live

    monkeypatch.setattr("chispa.config.LIVE_START", datetime(2026, 11, 21, tzinfo=UTC))
    monkeypatch.setattr("chispa.config.LIVE_POLL_LATE", timedelta(minutes=15))
    monkeypatch.setitem(config.AVAILABLE_DELAY, "viirs", timedelta(hours=3))
    live = tmp_path / "raw" / "live"
    (live / "polls").mkdir(parents=True)
    # Passes at 10:00 and 10:05. Then a stop to 20:00, and a pass at 20:05.
    (live / "polls" / "2026-11-21.csv").write_text(
        "polled_at,source,item,result,new_rows\n"
        + "".join(
            f"2026-11-21T{time}:00+00:00,firms,VIIRS_NOAA21_NRT,ok,1\n"
            for time in ("10:00", "10:05", "20:00", "20:05")
        )
    )
    header = (SAMPLES / "firms_VIIRS_SNPP_SP.csv").read_text().splitlines()[0]
    row = dict.fromkeys(header.split(","), "1") | {"satellite": "N21", "confidence": "n"}
    row |= {"latitude": "-17.5", "longitude": "-57.5", "acq_date": "2026-11-21"}
    rows = [
        row | {"acq_time": "0500", "first_seen_at": "2026-11-21T10:05:00+00:00"},  # no stop
        row | {"acq_time": "1300", "first_seen_at": "2026-11-21T20:00:00+00:00"},  # in the stop
        row | {"acq_time": "0600", "first_seen_at": "2026-11-21T20:00:00+00:00"},  # before it
        row | {"acq_time": "1830", "first_seen_at": "2026-11-21T20:00:00+00:00"},  # near its end
        row | {"acq_time": "1900", "first_seen_at": "2026-11-21T20:05:00+00:00"},  # no stop
    ]
    (live / "firms" / "VIIRS_NOAA21_NRT").mkdir(parents=True)
    with (live / "firms" / "VIIRS_NOAA21_NRT" / "2026-11-21.csv").open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (found,) = [detections for source, detections, _ in read_live(tmp_path / "raw")]

    def at(hour, minute=0):
        return datetime(2026, 11, 21, hour, minute, tzinfo=UTC)

    # Observation plus 3 hours, not before the pass of 10:05 and not after the first view.
    assert [(d.available_at, d.available_estimated) for d in found] == [
        (at(10, 5), False),
        (at(16), True),
        (at(10, 5), True),
        (at(20), True),
        (at(20, 5), False),
    ]


def test_update_reads_each_log_that_changed_and_no_other_log(tmp_path, monkeypatch):
    from chispa import build

    logs = tmp_path / "raw" / "live" / "goes"
    logs.mkdir(parents=True)
    header = "observed_at,lat,lon,mask,frp_mw,first_seen_at,published_at\n"

    def row(day, hour):
        start = f"2026-11-{day}T{hour}"
        return f"{start}:00:00+00:00,-17.5,-57.5,10,20.7,{start}:13:00+00:00,{start}:10:10+00:00\n"

    # The log of 1 November is old: a computer that was off for some weeks did not read it.
    (logs / "2026-11-01.csv").write_text(header + row("01", "15"))
    (logs / "2026-11-21.csv").write_text(header + row("21", "19"))
    read, read_log = [], build.read_log
    monkeypatch.setattr(
        build, "read_log", lambda *args: read.append(args[1].name) or read_log(*args)
    )
    store = open_store(tmp_path / "store.sqlite")
    assert build.add_live(tmp_path / "raw", store) == 2
    assert build.add_live(tmp_path / "raw", store) == 0
    assert read == ["2026-11-01.csv", "2026-11-21.csv"]  # the second update read no log
    # A pass with `--since` fills a hole in the old log. The update reads only that log again.
    with (logs / "2026-11-01.csv").open("a") as file:
        file.write(row("01", "16"))
    assert build.add_live(tmp_path / "raw", store) == 1
    assert read[2:] == ["2026-11-01.csv"]
