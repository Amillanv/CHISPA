"""Tests of the store build."""

import shutil
import sqlite3
from pathlib import Path

from chispa.build import build_store

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
    totals = build_store(tmp_path / "raw", tmp_path / "store.sqlite")
    # [files, detections, rejected rows]. The samples hold 4 + 4 + 4 FIRMS rows that we use.
    assert totals == {"firms": [3, 12, 0], "noaa": [1, 1, 0], "inpe": [1, 10, 0]}


def test_second_build_replaces_the_store(tmp_path):
    make_raw(tmp_path / "raw")
    build_store(tmp_path / "raw", tmp_path / "store.sqlite")
    shutil.rmtree(tmp_path / "raw" / "inpe")
    build_store(tmp_path / "raw", tmp_path / "store.sqlite")
    store = sqlite3.connect(tmp_path / "store.sqlite")
    assert store.execute("SELECT count(*) FROM detections").fetchone()[0] == 13
    assert not (tmp_path / "store.sqlite.building").exists()
