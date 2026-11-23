"""Tests of the live poller. They use no network: the source functions are replaced."""

import csv
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
    monkeypatch.setattr("chispa.sources.goes.list_live", lambda now: scans)
    monkeypatch.setattr(
        "chispa.sources.goes.read_live",
        lambda new: [
            (start, published, [[-17.5, -57.5, 10, 20.7]], {"no_fire": 90, "cloud": 10}, MASK)
            for _, start, published in new
        ],
    )
    monkeypatch.setattr("chispa.sources.inpe.list_live", lambda now: [])
    grid = (np.array([[-17.5, -17.5]]), np.array([[-57.5, -57.4]]))
    monkeypatch.setattr("chispa.sources.goes.mask_grid", lambda scan: grid)


def test_listing_gives_the_scan_time_and_the_publication_time():
    scans = goes.parse_listing((SAMPLES / "goes19_listing.xml").read_text())
    key, start, published_at = scans[0]
    assert len(scans) == 2
    assert key.endswith("_s20263251900215_e20263251909524_c20263251909594.nc")
    assert start == datetime(2026, 11, 21, 19, 0, tzinfo=UTC)
    assert published_at == datetime(2026, 11, 21, 19, 10, 10, tzinfo=UTC)


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


def test_inpe_file_is_read_one_time(tmp_path, monkeypatch):
    replace_sources(monkeypatch, [], [])
    name = "focos_10min_20261121_1920.csv"
    published_at = datetime(2026, 11, 21, 19, 20, 6, tzinfo=UTC)
    row = {"lat": "-17.5", "lon": "-57.5", "satelite": "NOAA-21", "data": "2026-11-21 16:56:00"}
    monkeypatch.setattr("chispa.sources.inpe.list_live", lambda now: [name])
    monkeypatch.setattr("chispa.sources.inpe.read_live", lambda name: (published_at, [row]))
    first = live.poll(tmp_path, "key", NOW)
    again = live.poll(tmp_path, "key", NOW + timedelta(minutes=5))
    log = read(tmp_path / "live" / "inpe" / "2026-11-21.csv")
    assert [result["item"] for result in first if result["source"] == "inpe"] == [name]
    assert [result for result in again if result["source"] == "inpe"] == []
    assert (log[0]["satelite"], log[0]["published_at"]) == ("NOAA-21", "2026-11-21T19:20:06+00:00")


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
    live._add_mask(folder, second, second + timedelta(minutes=12), MASK)
    day = np.load(folder / "2026-11-23.npz")
    assert day["times"].tolist() == [first.isoformat(), second.isoformat()]
    assert day["seen"].tolist() == ["2026-11-23T03:10:00+00:00", "2026-11-23T03:22:00+00:00"]
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
