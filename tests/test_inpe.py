"""Tests of the INPE parser against a small real file."""

import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from chispa.sources.inpe import dryness_rows, parse_file, year_files

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


def test_archive_rows_give_the_dryness_and_no_value_for_the_mark_of_inpe(tmp_path):
    rows = list(dryness_rows(ANNUAL))
    # 7 of the 8 rows are in the box. The first of them has 2 days with no rain, 1.2 mm and 0.1.
    assert len(rows) == 7
    assert rows[0] == (
        datetime(2019, 1, 1, 17, 36, tzinfo=UTC),
        -18.95416,
        -57.27932,
        2.0,
        1.2,
        0.1,
    )
    # The GOES-16 row has the mark -999 for the fire risk: no value.
    assert rows[3][3:] == (12.0, 0.1, None)
    # A monthly file has the same fields with other names for the time and the position.
    assert len(list(dryness_rows(SAMPLE))) == 10


def test_year_has_its_annual_file_or_its_monthly_files(tmp_path):
    (tmp_path / "inpe").mkdir()
    for name in (
        "focos_br_todos-sats_2019.zip",
        "focos_mensal_br_202301.zip",
        "focos_mensal_br_202302.csv",
    ):
        (tmp_path / "inpe" / name).write_text("")
    (tmp_path / "inpe" / "focos_mensal_br_202303.part").write_text("")
    assert [path.name for path in year_files(tmp_path, 2019)] == ["focos_br_todos-sats_2019.zip"]
    names = [path.name for path in year_files(tmp_path, 2023)]
    assert names == ["focos_mensal_br_202301.zip", "focos_mensal_br_202302.csv"]
