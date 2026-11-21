"""Tests of the evaluation, with cases small enough for paper."""

import numpy as np

from chispa.evaluate import first_times, match, measure
from chispa.grid import Grid

# A grid of 10 x 10 pixels of 0.001 degree (approximately 110 m) at the equator.
GRID = Grid(west=0.0, north=0.01, pixel_deg=0.001, width=10, height=10)


def numbers_grid():
    numbers = np.zeros((10, 10), dtype=np.int32)
    numbers[0, 0] = 1  # scar 1, in the north-west corner
    numbers[9, 9] = 2  # scar 2, in the south-east corner
    return numbers


def scar_fields(month, first_day=None, last_day=None):
    """Scar arrays with the scar number as the index. Index 0 is "no scar"."""
    count = len(month)
    return {
        "month": np.array([0, *month]),
        "first_day": np.array([0, *(first_day or [0] * count)]),
        "last_day": np.array([0, *(last_day or [0] * count)]),
    }


AUGUST = scar_fields(month=[8, 8])  # two scars of August, with no burn day


def detections(lat, lon, month, footprint_m=10.0, observed=None, available=None, day=None):
    count = len(lat)
    return {
        "lat": np.array(lat),
        "lon": np.array(lon),
        "month": np.array(month),
        "day": np.array(day or [0] * count),
        "footprint_m": np.full(count, footprint_m),
        "observed": np.array(observed or [0.0] * count),
        "available": np.array(available or [0.0] * count),
    }


def test_detection_on_a_scar_matches_it(monkeypatch):
    monkeypatch.setattr("chispa.config.EVAL_MARGIN_M", 0.0)
    found = detections(lat=[0.0095, 0.0055], lon=[0.0005, 0.0055], month=[8, 8])
    pair_detection, pair_scar = match(found, numbers_grid(), GRID, AUGUST)
    # The first detection is on scar 1. The second is in the centre, 400 m from each scar.
    assert (pair_detection.tolist(), pair_scar.tolist()) == ([0], [1])


def test_large_footprint_reaches_a_scar(monkeypatch):
    monkeypatch.setattr("chispa.config.EVAL_MARGIN_M", 0.0)
    found = detections(lat=[0.0055], lon=[0.0055], month=[8], footprint_m=600.0)
    pair_detection, pair_scar = match(found, numbers_grid(), GRID, AUGUST)
    assert pair_scar.tolist() == [1, 2]


def test_scar_with_no_burn_day_uses_its_month_and_the_month_before(monkeypatch):
    monkeypatch.setattr("chispa.config.EVAL_MARGIN_M", 0.0)
    monkeypatch.setattr("chispa.config.EVAL_MONTHS_BEFORE", 1)
    found = detections(lat=[0.0095] * 4, lon=[0.0005] * 4, month=[6, 7, 8, 9])
    pair_detection, _ = match(found, numbers_grid(), GRID, AUGUST)
    assert pair_detection.tolist() == [1, 2]  # July and August. Not June. Not September.


def test_scar_with_burn_days_uses_the_day_margin(monkeypatch):
    monkeypatch.setattr("chispa.config.EVAL_MARGIN_M", 0.0)
    monkeypatch.setattr("chispa.config.EVAL_DAY_MARGIN", 7)
    burned = scar_fields(month=[8, 8], first_day=[200, 0], last_day=[210, 0])
    # Scar 1 burned on the days 200 to 210. With the margin: 193 to 217.
    found = detections(lat=[0.0095] * 4, lon=[0.0005] * 4, month=[7] * 4, day=[192, 193, 217, 218])
    pair_detection, _ = match(found, numbers_grid(), GRID, burned)
    assert pair_detection.tolist() == [1, 2]


def test_first_time_is_the_earliest_chosen_detection():
    pairs = (np.array([0, 1, 2]), np.array([1, 1, 2]))
    times = np.array([50.0, 20.0, 70.0])
    first = first_times(pairs, np.array([True, True, False]), times, scar_count=2)
    assert first.tolist() == [np.inf, 20.0, np.inf]


def test_measures_of_one_configuration(monkeypatch):
    monkeypatch.setattr("chispa.config.EVAL_MIN_SCAR_HA", 10.0)
    # Three detections: 0 and 1 match scar 1, 2 matches no scar. Scar 2 gets no detection.
    found = detections(
        [0.0] * 3, [0.0] * 3, [8] * 3, observed=[0, 7200, 0], available=[3600, 9000, 0]
    )
    pairs = (np.array([0, 1]), np.array([1, 1]))
    in_year = np.array([False, True, True])
    scars = {"area_ha": np.array([0.0, 100.0, 300.0]), "in_year": in_year, "counted": in_year}
    reference = (np.array([np.inf, 0.0, np.inf]), np.array([np.inf, 3600.0, np.inf]))
    late_only = np.array([False, True, True])
    row = measure("late", late_only, found, pairs, scars, reference)
    assert (row["detections"], row["unmatched_detections"], row["unmatched_share"]) == (2, 1, 0.5)
    assert (row["scars"], row["scars_found"], row["scar_recall"]) == (2, 1, 0.5)
    assert row["area_recall"] == 0.25  # 100 of 400 hectares
    assert row["delay_observed_h_median"] == 2.0  # 7200 s after the first detection
    assert row["delay_available_h_median"] == 1.5  # 9000 s against 3600 s
