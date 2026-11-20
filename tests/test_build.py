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
