"""Tests of the INPE parser against a small real file."""

import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from chispa.sources.inpe import parse_file

SAMPLE = Path(__file__).parent / "samples" / "inpe_202302.csv"
ANNUAL = Path(__file__).parent / "samples" / "inpe_anual_sample.csv"


def test_only_rows_in_the_box_become_detections():
    detections, rejected, unused = parse_file(SAMPLE)
    # The file has 11 rows. The first row is in Roraima, far from the Pantanal.
    assert (len(detections), rejected, dict(unused)) == (10, 0, {})


def test_satellite_name_gives_family_and_platform():
    detections, _, _ = parse_file(SAMPLE)
    pairs = {(d.sensor_family, d.platform) for d in detections}
    assert pairs == {
        ("modis", "AQUA"),
        ("modis", "TERRA"),
        ("viirs", "NOAA20"),
        ("viirs", "SNPP"),
        ("abi", "GOES16"),
        ("avhrr", "METOPB"),
        ("avhrr", "NOAA19"),
    }


def test_row_values():
    first = parse_file(SAMPLE)[0][0]
    assert first.observed_at == datetime(2023, 2, 1, 17, 9, tzinfo=UTC)
    assert first.available_at - first.observed_at == timedelta(hours=3)
    assert (first.lat, first.lon, first.frp_mw) == (-17.1344, -54.72765, 18.7)
    assert (first.source, first.source_confidence) == ("inpe", "nominal")


def test_absent_power_is_none():
    metop = parse_file(SAMPLE)[0][4]
    assert (metop.platform, metop.frp_mw) == ("METOPB", None)


def test_zip_file_gives_the_same_detections(tmp_path):
    path = tmp_path / "focos.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.write(SAMPLE, "focos.csv")
    assert parse_file(path)[0] == parse_file(SAMPLE)[0]


def test_annual_file_has_other_field_names():
    detections, rejected, unused = parse_file(ANNUAL)
    # The file has 8 rows of 2019. One is in Paraíba. We do not use NOAA-15 and MSG-03.
    assert (len(detections), rejected, dict(unused)) == (5, 0, {"NOAA-15": 1, "MSG-03": 1})
    first = detections[0]
    assert (first.platform, first.lat, first.lon, first.frp_mw) == (
        "SNPP",
        -18.95416,
        -57.27932,
        6.6,
    )
    assert first.observed_at == datetime(2019, 1, 1, 17, 36, tzinfo=UTC)
    assert detections[2].frp_mw is None
