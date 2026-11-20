"""Tests of the FIRMS parser against small real files."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from chispa.sources.firms import parse_file

SAMPLES = Path(__file__).parent / "samples"


def test_viirs_row_becomes_a_detection():
    detections, rejected = parse_file(SAMPLES / "firms_VIIRS_SNPP_SP.csv", "VIIRS_SNPP_SP")
    first = detections[0]
    assert (len(detections), rejected) == (4, 0)
    assert (first.platform, first.sensor_family) == ("SNPP", "viirs")
    assert first.observed_at == datetime(2024, 8, 15, 5, 13, tzinfo=UTC)
    assert first.available_at - first.observed_at == timedelta(hours=3)
    assert (first.lat, first.lon) == (-17.33096, -57.44352)
    assert first.footprint_m == 215.0  # scan 0.43 km, track 0.38 km
    assert (first.frp_mw, first.source_confidence) == (1.04, "nominal")


def test_modis_percentage_becomes_a_confidence_class():
    detections, _ = parse_file(SAMPLES / "firms_MODIS_SP.csv", "MODIS_SP")
    assert detections[0].platform == "TERRA"
    assert detections[0].source_confidence == "nominal"  # 66 percent
    assert detections[0].footprint_m == 700.0  # scan 1.4 km


def test_goes_file_keeps_only_the_g16_rows():
    detections, rejected = parse_file(SAMPLES / "firms_GOES_NRT.csv", "GOES_NRT")
    assert rejected == 0
    assert [d.platform for d in detections] == ["GOES16"] * 4
    assert detections[0].observed_at == datetime(2024, 8, 15, 0, 0, tzinfo=UTC)
    assert detections[0].available_at - detections[0].observed_at == timedelta(minutes=30)


def test_goes_missing_power_is_none():
    detections, _ = parse_file(SAMPLES / "firms_GOES_NRT.csv", "GOES_NRT")
    assert detections[-1].frp_mw is None


def test_bad_row_is_counted_and_not_kept(tmp_path):
    lines = (SAMPLES / "firms_VIIRS_SNPP_SP.csv").read_text().splitlines()
    lines[1] = lines[1].replace("-17.33096", "-917.33096")
    path = tmp_path / "bad.csv"
    path.write_text("\n".join(lines))
    detections, rejected = parse_file(path, "VIIRS_SNPP_SP")
    assert (len(detections), rejected) == (3, 1)
