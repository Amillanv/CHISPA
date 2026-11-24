"""Tests of the detection record."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from chispa.models import Detection

NOON = datetime(2024, 8, 15, 12, 0, tzinfo=UTC)
GOOD = Detection(
    source="firms",
    sensor_family="viirs",
    platform="SNPP",
    observed_at=NOON,
    available_at=NOON + timedelta(hours=3),
    lat=-17.5,
    lon=-57.5,
    footprint_m=375.0,
    frp_mw=None,
    source_confidence="nominal",
    available_estimated=True,
)


@pytest.mark.parametrize(
    "change",
    [
        {"sensor_family": "radar"},
        {"source_confidence": "n"},
        {"lat": -95.0},
        {"lon": 190.0},
        {"footprint_m": 0.0},
        {"observed_at": datetime(2024, 8, 15, 12, 0)},
        {"available_at": NOON - timedelta(minutes=1)},
    ],
)
def test_bad_record_is_rejected(change):
    with pytest.raises(ValueError):
        replace(GOOD, **change)
