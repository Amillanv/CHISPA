"""Tests of the raw GOES module."""

from datetime import UTC, datetime
from types import SimpleNamespace

import numpy as np

from chispa.sources.goes import parse_file, to_lat_lon

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
