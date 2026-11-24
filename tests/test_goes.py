"""Tests of the raw GOES module."""

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from chispa.sources import goes
from chispa.sources.goes import parse_file, to_lat_lon

SAMPLES = Path(__file__).parent / "samples"
NOW = datetime(2026, 11, 21, 19, 30, tzinfo=UTC)  # the time of a pass of the live poller

# The constants of the GOES-East projection, from a raw file.
PROJECTION = SimpleNamespace(
    semi_major_axis=6378137.0,
    semi_minor_axis=6356752.31414,
    perspective_point_height=35786023.0,
    longitude_of_projection_origin=-75.0,
)


def test_centre_of_the_grid_is_the_point_below_the_satellite():
    lat, lon = to_lat_lon(np.array([0.0]), np.array([0.0]), PROJECTION)
    assert (round(float(lat[0]), 9), round(float(lon[0]), 9)) == (0.0, -75.0)


def test_point_off_the_earth_gives_nan():
    lat, _ = to_lat_lon(np.array([0.3]), np.array([0.3]), PROJECTION)
    assert np.isnan(lat[0])


def test_day_file_becomes_detections(tmp_path):
    path = tmp_path / "2024-10-01.csv"
    path.write_text(
        "observed_at,lat,lon,mask,frp_mw\n"
        "2024-10-01T15:00:00+00:00,-17.5,-57.5,30,20.7\n"
        "2024-10-01T15:00:00+00:00,-17.6,-57.5,11,\n"
    )
    first, saturated = parse_file(path, "GOES16")
    assert (first.source, first.platform, first.sensor_family) == ("noaa", "GOES16", "abi")
    assert first.observed_at == datetime(2024, 10, 1, 15, 0, tzinfo=UTC)
    assert (first.frp_mw, saturated.frp_mw) == (20.7, None)


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


def test_listing_is_of_the_utc_day_of_each_limit(monkeypatch):
    asked = []

    class Answer:
        text = ""

    monkeypatch.setattr("chispa.sources.goes._get", lambda url: asked.append(url) or Answer())
    # 01:00 at +02:00 on 22 November is 23:00 UTC on 21 November: day 325, then day 326.
    since = datetime(2026, 11, 22, 1, tzinfo=timezone(timedelta(hours=2)))
    goes.list_live(since, datetime(2026, 11, 22, 0, 30, tzinfo=UTC))
    assert [url[-9:] for url in asked] == ["2026/325/", "2026/326/"]
