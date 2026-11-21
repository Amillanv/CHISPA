"""Tests of the store build."""

import shutil
from pathlib import Path

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


def test_live_log_gives_the_time_of_the_first_view_as_available_at(tmp_path):
    from datetime import UTC, datetime

    from chispa.build import read_live

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
    found = {source: detections[0] for source, detections, _ in read_live(tmp_path / "raw", "")}
    assert (found["noaa"].platform, found["inpe"].platform) == ("GOES19", "NOAA21")
    assert found["noaa"].available_at == datetime(2026, 11, 21, 19, 15, tzinfo=UTC)
    assert found["inpe"].available_at == datetime(2026, 11, 21, 20, 48, 58, tzinfo=UTC)
    assert list(read_live(tmp_path / "raw", "2026-11-22")) == []  # a log of an earlier day
