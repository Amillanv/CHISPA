"""Tests of the live poller. They use no network: the source functions are replaced."""

import csv
import gzip
import types
from datetime import UTC, datetime, timedelta, timezone

import numpy as np

from chispa import live

NOW = datetime(2026, 11, 21, 19, 30, tzinfo=UTC)
ROW = {
    "latitude": "-17.5",
    "longitude": "-57.5",
    "acq_date": "2026-11-21",
    "acq_time": "1656",
    "satellite": "N21",
    "frp": "4.2",
}
SCAN = (
    "a/key.nc",
    datetime(2026, 11, 21, 19, 0, tzinfo=UTC),
    datetime(2026, 11, 21, 19, 10, tzinfo=UTC),
)


def read(path):
    with path.open(newline="") as file:
        return list(csv.DictReader(file))


MASK = np.array([[100, 200]], dtype=np.uint8)  # one pixel examined, one pixel with cloud


def replace_sources(monkeypatch, firms_rows, scans):
    """One FIRMS product that gives `firms_rows`, and GOES scans with one fire pixel each."""
    monkeypatch.setattr("chispa.sources.firms.LIVE_PRODUCTS", {"VIIRS_NOAA21_NRT": "viirs"})
    monkeypatch.setattr("chispa.sources.firms.download_live", lambda product, key: firms_rows)
    monkeypatch.setattr("chispa.sources.goes.list_live", lambda since, now: scans)
    monkeypatch.setattr(
        "chispa.sources.goes.read_live",
        lambda new: [
            (start, published, [[-17.5, -57.5, 10, 20.7]], {"no_fire": 90, "cloud": 10}, MASK)
            for _, start, published in new
        ],
    )
    monkeypatch.setattr("chispa.sources.inpe.list_live", lambda since, now: [])
    grid = (np.array([[-17.5, -17.5]]), np.array([[-57.5, -57.4]]))
    monkeypatch.setattr("chispa.sources.goes.mask_grid", lambda scan: grid)


def test_row_of_a_long_pass_has_the_time_of_its_read(tmp_path, monkeypatch):
    # The file of the scan comes 2 minutes after the start of the pass, and the pass reads it later.
    late = ("d/key.nc", NOW - timedelta(minutes=8), NOW + timedelta(minutes=2))
    replace_sources(monkeypatch, [], [late])
    ticks = iter(range(0, 6000, 300))  # Each look at the clock is 5 minutes after the one before.
    monkeypatch.setattr("chispa.live.time", types.SimpleNamespace(monotonic=lambda: next(ticks)))
    live.poll(tmp_path, "key", NOW)
    log = read(tmp_path / "live" / "goes" / "2026-11-21.csv")
    polls = read(tmp_path / "live" / "polls" / "2026-11-21.csv")
    # The row has the time of its read, not the start of the pass: that is before the publication.
    assert (log[0]["published_at"], log[0]["first_seen_at"]) == (
        "2026-11-21T19:32:00+00:00",
        "2026-11-21T19:40:00+00:00",
    )
    assert {row["polled_at"] for row in polls} == {NOW.isoformat()}


def test_pass_reads_back_the_lookback_or_to_a_given_time(tmp_path, monkeypatch):
    replace_sources(monkeypatch, [], [])
    monkeypatch.setattr("chispa.config.LIVE_LOOKBACK", timedelta(days=4))
    monkeypatch.setattr("chispa.config.LIVE_START", datetime(2026, 10, 1, tzinfo=UTC))
    asked = []
    monkeypatch.setattr(
        "chispa.sources.goes.list_live", lambda since, now: asked.append(since) or []
    )
    live.poll(tmp_path, "key", NOW)
    # A time with a different offset: 02:00 at +02:00 is 00:00 UTC. The pass uses the UTC time.
    live.poll(tmp_path, "key", NOW, datetime(2026, 11, 1, 2, tzinfo=timezone(timedelta(hours=2))))
    # A pass does not read back to before the start of the live logs.
    live.poll(tmp_path, "key", NOW, datetime(2026, 9, 1, tzinfo=UTC))
    assert asked == [
        NOW - timedelta(days=4),
        datetime(2026, 11, 1, tzinfo=UTC),
        datetime(2026, 10, 1, tzinfo=UTC),
    ]
    assert [since.utcoffset() for since in asked] == [timedelta(0)] * 3


def test_scan_of_a_stop_is_read_when_the_poller_is_back(tmp_path, monkeypatch):
    replace_sources(monkeypatch, [], [SCAN])
    live.poll(tmp_path, "key", NOW)
    # The poller stops for two days. The bucket then lists the old scan and two new scans.
    back = NOW + timedelta(days=2)
    missed = ("b/key.nc", SCAN[1] + timedelta(hours=20), SCAN[2] + timedelta(hours=20))
    newest = ("c/key.nc", back - timedelta(minutes=20), back - timedelta(minutes=10))
    replace_sources(monkeypatch, [], [SCAN, missed, newest])
    results = live.poll(tmp_path, "key", back)
    # The scan that a pass read two days before is not read again.
    assert [result["item"] for result in results if result["source"] == "goes"] == [
        missed[1].isoformat(),
        newest[1].isoformat(),
    ]
    log = read(tmp_path / "live" / "goes" / "2026-11-22.csv")
    assert (log[0]["published_at"], log[0]["first_seen_at"]) == (
        missed[2].isoformat(),
        back.isoformat(),
    )


def test_row_keeps_the_time_of_the_first_pass_that_saw_it(tmp_path, monkeypatch):
    replace_sources(monkeypatch, [ROW], [])
    first = live.poll(tmp_path, "key", NOW)
    later_row = {**ROW, "acq_time": "1658"}
    replace_sources(monkeypatch, [ROW, later_row], [])
    second = live.poll(tmp_path, "key", NOW + timedelta(minutes=5))
    log = read(tmp_path / "live" / "firms" / "VIIRS_NOAA21_NRT" / "2026-11-21.csv")
    assert (first[0]["new_rows"], second[0]["new_rows"]) == (1, 1)
    assert [(row["acq_time"], row["first_seen_at"]) for row in log] == [
        ("1656", "2026-11-21T19:30:00+00:00"),
        ("1658", "2026-11-21T19:35:00+00:00"),
    ]


def test_goes_scan_is_read_one_time(tmp_path, monkeypatch):
    replace_sources(monkeypatch, [], [SCAN])
    live.poll(tmp_path, "key", NOW)
    again = live.poll(tmp_path, "key", NOW + timedelta(minutes=5))
    log = read(tmp_path / "live" / "goes" / "2026-11-21.csv")
    seen = read(tmp_path / "live" / "goes_mask" / "2026-11-21.csv")
    assert [(row["no_fire"], row["cloud"]) for row in seen] == [("90", "10")] * len(seen)
    assert len(seen) == len({row["observed_at"] for row in log})
    # The mask of each scan is in the file of its day, in the form of the recorded masks.
    day = np.load(tmp_path / "live" / "goes_mask" / "2026" / "2026-11-21.npz")
    assert (len(day["times"]), day["mask"].shape) == (len(seen), (len(seen), 1, 2))
    assert (tmp_path / "live" / "goes_mask" / "grid.npz").exists()
    assert [result for result in again if result["source"] == "goes"] == []
    assert len(log) == 1
    assert (log[0]["observed_at"], log[0]["published_at"]) == (
        "2026-11-21T19:00:00+00:00",
        "2026-11-21T19:10:00+00:00",
    )
    assert log[0]["first_seen_at"] == "2026-11-21T19:30:00+00:00"


def test_each_pass_is_in_the_poll_log(tmp_path, monkeypatch):
    replace_sources(monkeypatch, [ROW], [SCAN])
    live.poll(tmp_path, "key", NOW)
    polls = read(tmp_path / "live" / "polls" / "2026-11-21.csv")
    # The last row says that the pass read each source: a pass that stops has no such row.
    assert [(row["source"], row["result"], row["new_rows"]) for row in polls] == [
        ("firms", "ok", "1"),
        ("goes", "ok", "1"),
        ("pass", "ok", "2"),
    ]


def test_source_that_fails_does_not_stop_the_pass(tmp_path, monkeypatch):
    replace_sources(monkeypatch, [], [SCAN])

    def fail(product, key):
        raise RuntimeError("FIRMS request failed (VIIRS_NOAA21_NRT): Timeout")

    monkeypatch.setattr("chispa.sources.firms.download_live", fail)
    results = live.poll(tmp_path, "key", NOW)
    assert [(result["source"], result["result"][:6]) for result in results] == [
        ("firms", "failed"),
        ("goes", "ok"),
        ("pass", "ok"),
    ]


def test_inpe_file_is_read_one_time_and_kept_in_full(tmp_path, monkeypatch):
    replace_sources(monkeypatch, [], [])
    name = "focos_10min_20261121_1920.csv"
    published_at = datetime(2026, 11, 21, 19, 20, 6, tzinfo=UTC)
    # One row in the Pantanal box, and one row in a different region.
    content = (
        b"lat,lon,satelite,data\n"
        b"-17.5,-57.5,NOAA-21,2026-11-21 16:56:00\n"
        b"-3.1,-60.0,NOAA-21,2026-11-21 16:58:00\n"
    )
    monkeypatch.setattr("chispa.sources.inpe.list_live", lambda since, now: [name])
    monkeypatch.setattr("chispa.sources.inpe.read_live", lambda name: (published_at, content))
    first = live.poll(tmp_path, "key", NOW)
    again = live.poll(tmp_path, "key", NOW + timedelta(minutes=5))
    log = read(tmp_path / "live" / "inpe" / "2026-11-21.csv")
    assert [(r["item"], r["new_rows"]) for r in first if r["source"] == "inpe"] == [(name, 1)]
    assert [result for result in again if result["source"] == "inpe"] == []
    assert [(row["lat"], row["published_at"]) for row in log] == [
        ("-17.5", "2026-11-21T19:20:06+00:00")
    ]
    # The full file has the two rows, and the list of the day has its times.
    files = tmp_path / "live" / "inpe_files"
    assert gzip.decompress((files / "2026-11-21" / f"{name}.gz").read_bytes()) == content
    assert read(files / "2026-11-21.csv") == [
        {
            "file": name,
            "first_seen_at": "2026-11-21T19:30:00+00:00",
            "published_at": "2026-11-21T19:20:06+00:00",
        }
    ]


def test_mask_file_with_no_time_of_the_first_view_gets_an_estimate(tmp_path, monkeypatch):
    monkeypatch.setattr("chispa.config.GOES_RAW_DELAY", timedelta(minutes=10))
    folder = tmp_path / "2026"
    folder.mkdir()
    first = datetime(2026, 11, 23, 3, 0, tzinfo=UTC)
    # A file that an earlier version of the poller made: it has no `seen`.
    np.savez(folder / "2026-11-23.npz", times=np.array([first.isoformat()]), mask=MASK[None])
    second = first + timedelta(minutes=10)
    times = live._times(second + timedelta(minutes=12), second + timedelta(minutes=11))
    live._add_mask(folder, second, times, MASK)
    day = np.load(folder / "2026-11-23.npz")
    assert day["times"].tolist() == [first.isoformat(), second.isoformat()]
    assert day["seen"].tolist() == ["2026-11-23T03:10:00+00:00", "2026-11-23T03:22:00+00:00"]
    # The old scan has the same estimate for its publication time. The new scan has its own time.
    assert day["published"].tolist() == ["2026-11-23T03:10:00+00:00", "2026-11-23T03:21:00+00:00"]
    assert day["mask"].shape == (2, 1, 2)


def test_mask_of_a_scan_is_in_its_file_one_time(tmp_path):
    scan = datetime(2026, 11, 23, 3, 0, tzinfo=UTC)
    times = live._times(scan + timedelta(minutes=12), scan + timedelta(minutes=10))
    # A pass that stopped after this write reads the scan again.
    live._add_mask(tmp_path, scan, times, MASK)
    live._add_mask(tmp_path, scan, times, MASK)
    assert np.load(tmp_path / "2026-11-23.npz")["times"].tolist() == [scan.isoformat()]


def test_pass_after_a_long_stop_reads_back_to_the_newest_scan_that_a_pass_read(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("chispa.config.LIVE_LOOKBACK", timedelta(days=4))
    replace_sources(
        monkeypatch, [], [SCAN]
    )  # The last pass before the stop read the scan of 19:00.
    live.poll(tmp_path, "key", NOW)
    # The file of the scan of 19:20 came after that pass. The poller is back 4 days later, at
    # 19:25: the time 4 days before it is after the start of that scan.
    waiting = ("b/key.nc", SCAN[1] + timedelta(minutes=20), NOW + timedelta(minutes=1))
    back, asked = NOW + timedelta(days=4, minutes=-5), []
    monkeypatch.setattr(
        "chispa.sources.goes.list_live", lambda since, now: asked.append(since) or [SCAN, waiting]
    )
    results = live.poll(tmp_path, "key", back)
    assert asked == [SCAN[1]]
    assert [r["item"] for r in results if r["source"] == "goes"] == [waiting[1].isoformat()]


def test_pass_reads_inpe_before_the_read_back_of_goes(tmp_path, monkeypatch):
    replace_sources(monkeypatch, [], [SCAN])
    name = "focos_10min_20261121_1920.csv"
    content = b"lat,lon,satelite,data\n-17.5,-57.5,NOAA-21,2026-11-21 16:56:00\n"
    monkeypatch.setattr("chispa.sources.inpe.list_live", lambda since, now: [name])
    monkeypatch.setattr("chispa.sources.inpe.read_live", lambda name: (NOW, content))
    # INPE removes its files after some days. The NOAA bucket keeps each scan.
    results = live.poll(tmp_path, "key", NOW)
    assert [result["source"] for result in results] == ["firms", "inpe", "goes", "pass"]


def test_inpe_file_that_a_pass_reads_again_is_in_the_logs_one_time(tmp_path):
    name = "focos_10min_20261121_1920.csv"
    content = b"lat,lon,satelite,data\n-17.5,-57.5,NOAA-21,2026-11-21 16:56:00\n"
    first = live._times(NOW, NOW - timedelta(minutes=10))
    # A pass stopped after the writes of the file. The next pass reads the file again, later.
    assert live.keep_inpe(tmp_path, name, content, first) == 1
    assert (
        live.keep_inpe(tmp_path, name, content, live._times(NOW + timedelta(minutes=5), NOW)) == 1
    )
    listed = read(tmp_path / "inpe_files" / "2026-11-21.csv")
    assert [(row["file"], row["first_seen_at"]) for row in listed] == [(name, NOW.isoformat())]
    assert len(read(tmp_path / "inpe" / "2026-11-21.csv")) == 1


def test_key_does_not_go_into_the_poll_log(tmp_path, monkeypatch):
    replace_sources(monkeypatch, [], [])

    def fail(product, key):
        raise RuntimeError(f"FIRMS request failed ({product}): HTTP 400 'bad url /csv/{key}/x'")

    monkeypatch.setattr("chispa.sources.firms.download_live", fail)
    live.poll(tmp_path, "secret-key", NOW)
    text = (tmp_path / "live" / "polls" / "2026-11-21.csv").read_text()
    assert "secret-key" not in text
    assert "bad url /csv/[key]/x" in text


def test_firms_row_from_before_the_live_logs_is_not_in_a_live_log(tmp_path, monkeypatch):
    monkeypatch.setattr("chispa.config.LIVE_START", datetime(2026, 11, 21, tzinfo=UTC))
    # A request gives 5 days. The row of 20 November is of the archive.
    replace_sources(monkeypatch, [{**ROW, "acq_date": "2026-11-20"}, ROW], [])
    results = live.poll(tmp_path, "key", NOW)
    logs = sorted(path.name for path in (tmp_path / "live" / "firms").glob("*/*.csv"))
    assert (results[0]["new_rows"], logs) == (1, ["2026-11-21.csv"])
