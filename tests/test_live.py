"""Tests of the live poller. They use no network: the source functions are replaced."""

import csv
import gzip
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

from chispa import live
from chispa.sources import goes

SAMPLES = Path(__file__).parent / "samples"
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


def test_listing_gives_the_scan_time_and_the_publication_time():
    scans = goes.parse_listing((SAMPLES / "goes19_listing.xml").read_text())
    key, start, published_at = scans[0]
    assert len(scans) == 2
    assert key.endswith("_s20263251900215_e20263251909524_c20263251909594.nc")
    assert start == datetime(2026, 11, 21, 19, 0, tzinfo=UTC)
    assert published_at == datetime(2026, 11, 21, 19, 10, 10, tzinfo=UTC)


def test_listing_gives_the_scans_from_a_time(monkeypatch):
    listing = (SAMPLES / "goes19_listing.xml").read_text()
    asked = []

    class Answer:
        text = listing

    monkeypatch.setattr("chispa.sources.goes._get", lambda url: asked.append(url) or Answer())
    since = datetime(2026, 11, 20, 19, 5, tzinfo=UTC)
    # One listing for each day from the day of `since`. The sample has the scans of 21 November.
    scans = goes.list_live(since, NOW)
    assert [url[-9:] for url in asked] == ["2026/324/", "2026/325/"]
    assert [scan[1].isoformat() for scan in scans] == [
        "2026-11-21T19:00:00+00:00",
        "2026-11-21T19:10:00+00:00",
    ]
    late = datetime(2026, 11, 21, 19, 5, tzinfo=UTC)
    assert [scan[1].minute for scan in goes.list_live(late, NOW)] == [10]


def test_listing_keeps_the_first_file_of_a_scan_and_no_scan_after_now(monkeypatch):
    def entry(start, created, modified):
        key = f"ABI-L2-FDCF/2026/325/19/OR_ABI-L2-FDCF-M6_G19_s2026325{start}215_c{created}.nc"
        modified = f"<LastModified>2026-11-21T{modified}.000Z</LastModified>"
        return f"<Contents><Key>{key}</Key>{modified}</Contents>"

    class Answer:
        # The scan of 19:00 has two files, and the bucket lists the later file first.
        # The scan of 19:40 starts after the time of the pass.
        text = (
            entry("1900", "20263251924000", "19:25:00")
            + entry("1900", "20263251909594", "19:10:10")
            + entry("1940", "20263251949594", "19:50:10")
        )

    monkeypatch.setattr("chispa.sources.goes._get", lambda url: Answer())
    scans = goes.list_live(NOW - timedelta(hours=1), NOW)
    assert [(scan[1].minute, scan[2].minute) for scan in scans] == [(0, 10)]


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
    asked = []
    monkeypatch.setattr(
        "chispa.sources.goes.list_live", lambda since, now: asked.append(since) or []
    )
    live.poll(tmp_path, "key", NOW)
    live.poll(tmp_path, "key", NOW, datetime(2026, 11, 1, tzinfo=UTC))
    assert asked == [NOW - timedelta(days=4), datetime(2026, 11, 1, tzinfo=UTC)]


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
    assert [(row["source"], row["result"], row["new_rows"]) for row in polls] == [
        ("firms", "ok", "1"),
        ("goes", "ok", "1"),
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


def test_only_a_log_that_gets_no_more_rows_is_complete(tmp_path, monkeypatch):
    monkeypatch.setattr("chispa.config.LIVE_COMPLETE_AFTER", timedelta(days=2))
    for day in ("2026-11-19", "2026-11-20", "2026-11-21"):
        path = tmp_path / "live" / "goes" / f"{day}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("observed_at\n")
    # At 19:30 on 21 November, the log of 19 November is 2 days old. The log of 20 November is not.
    assert [path.stem for path in live.complete_logs(tmp_path, NOW)] == ["2026-11-19"]


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
        return live.status(tmp_path, datetime.fromisoformat(text))

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
        return live.answered_before(tmp_path, datetime.fromisoformat(text), source).isoformat()

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
