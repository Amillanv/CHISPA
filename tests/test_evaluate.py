"""Tests of the evaluation, with cases small enough for paper."""

import numpy as np

from chispa.evaluation.events import event_table, split_table
from chispa.evaluation.match import first_times, isolated, match
from chispa.evaluation.recall import gain_table, measure
from chispa.grid import Grid

# A grid of 10 x 10 pixels of 0.001 degree (approximately 110 m) at the equator.
GRID = Grid(west=0.0, north=0.01, pixel_deg=0.001, width=10, height=10)


def numbers_grid():
    numbers = np.zeros((10, 10), dtype=np.int32)
    numbers[0, 0] = 1  # fire 1, in the north-west corner
    numbers[9, 9] = 2  # fire 2, in the south-east corner
    return numbers


def fire_fields(month, first_day=None, last_day=None):
    """Fire arrays with the fire number as the index. Index 0 is "no fire"."""
    count = len(month)
    return {
        "month": np.array([0, *month]),
        "first_day": np.array([0, *(first_day or [0] * count)]),
        "last_day": np.array([0, *(last_day or [0] * count)]),
    }


AUGUST = fire_fields(month=[8, 8])  # two fires of August, with no burn day


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


def test_detection_on_a_fire_matches_it(monkeypatch):
    monkeypatch.setattr("chispa.config.EVAL_MARGIN_M", 0.0)
    found = detections(lat=[0.0095, 0.0055], lon=[0.0005, 0.0055], month=[8, 8])
    pair_detection, pair_fire = match(found, numbers_grid(), GRID, AUGUST)
    # The first detection is on fire 1. The second is in the centre, 400 m from each fire.
    assert (pair_detection.tolist(), pair_fire.tolist()) == ([0], [1])


def test_large_footprint_reaches_a_fire(monkeypatch):
    monkeypatch.setattr("chispa.config.EVAL_MARGIN_M", 0.0)
    found = detections(lat=[0.0055], lon=[0.0055], month=[8], footprint_m=600.0)
    pair_detection, pair_fire = match(found, numbers_grid(), GRID, AUGUST)
    assert pair_fire.tolist() == [1, 2]


def test_fire_with_no_burn_day_uses_its_month_and_the_month_before(monkeypatch):
    monkeypatch.setattr("chispa.config.EVAL_MARGIN_M", 0.0)
    monkeypatch.setattr("chispa.config.EVAL_MONTHS_BEFORE", 1)
    found = detections(lat=[0.0095] * 4, lon=[0.0005] * 4, month=[6, 7, 8, 9])
    pair_detection, _ = match(found, numbers_grid(), GRID, AUGUST)
    assert pair_detection.tolist() == [1, 2]  # July and August. Not June. Not September.


def test_fire_with_burn_days_uses_the_day_margin(monkeypatch):
    monkeypatch.setattr("chispa.config.EVAL_MARGIN_M", 0.0)
    monkeypatch.setattr("chispa.config.EVAL_DAY_MARGIN", 7)
    burned = fire_fields(month=[0, 8], first_day=[200, 0], last_day=[210, 0])
    # Fire 1 burned on the days 200 to 210. With the margin: 193 to 217.
    found = detections(lat=[0.0095] * 4, lon=[0.0005] * 4, month=[7] * 4, day=[192, 193, 217, 218])
    pair_detection, _ = match(found, numbers_grid(), GRID, burned)
    assert pair_detection.tolist() == [1, 2]


def test_first_time_is_the_earliest_chosen_detection():
    pairs = (np.array([0, 1, 2]), np.array([1, 1, 2]))
    times = np.array([50.0, 20.0, 70.0])
    first = first_times(pairs, np.array([True, True, False]), times, count=2)
    assert first.tolist() == [np.inf, 20.0, np.inf]


def test_fire_that_shares_a_detection_is_not_isolated():
    # Detection 0 matches the fires 1 and 2. Detection 1 matches only fire 3.
    pairs = (np.array([0, 0, 1]), np.array([1, 2, 3]))
    all_counted = {"counted": np.array([False, True, True, True])}
    assert isolated(pairs, all_counted).tolist() == [False, False, False, True]
    # A fire that is too small to count does not remove the isolation of fire 1.
    small_second = {"counted": np.array([False, True, False, True])}
    assert isolated(pairs, small_second).tolist() == [False, True, False, True]


# Three detections: 0 and 1 match fire 1, 2 matches no fire. Fire 2 gets no detection.
PAIRS = (np.array([0, 1]), np.array([1, 1]))
FOUND = detections([0.0] * 3, [0.0] * 3, [8] * 3, observed=[0, 7200, 0], available=[3600, 9000, 0])


def two_fires(isolated_fires):
    return {
        "area_ha": np.array([0.0, 100.0, 300.0]),
        "first_day": np.array([0, 220, 0]),
        "counted": np.array([False, True, True]),
        "isolated": np.array([False, *isolated_fires]),
    }


def test_measures_of_one_configuration():
    late_only = np.array([False, True, True])
    row = measure("late", late_only, FOUND, PAIRS, two_fires([True, True]))
    assert (row["detections"], row["unmatched_detections"], row["unmatched_share"]) == (2, 1, 0.5)
    assert (row["fires"], row["fires_found"], row["fire_recall"]) == (2, 1, 0.5)
    assert row["area_recall"] == 0.25  # 100 of 400 hectares
    assert row["delay_fires"] == 1
    assert row["delay_observed_h_median"] == 2.0  # 7200 s after the first detection
    assert row["delay_available_h_median"] == 1.5  # 9000 s against 3600 s


def test_configuration_gives_the_first_and_the_last_day_of_its_detections():
    # Three detections: on day 1, day 3 and day 41 of 1970. The configuration has the last two.
    day_s = 86_400
    found = detections([0.0] * 3, [0.0] * 3, [8] * 3, observed=[0, 2 * day_s, 40 * day_s + 60])
    row = measure("part", np.array([False, True, True]), found, PAIRS, two_fires([True, True]))
    assert (row["first_day"], row["last_day"]) == ("1970-01-03", "1970-02-10")
    empty = measure("none", np.array([False, False, False]), found, PAIRS, two_fires([True, True]))
    assert (empty["first_day"], empty["last_day"]) == (None, None)


def test_fire_that_is_not_isolated_gives_no_delay():
    row = measure("late", np.array([False, True, True]), FOUND, PAIRS, two_fires([False, True]))
    assert (row["fires_found"], row["delay_fires"]) == (1, 0)
    assert row["delay_observed_h_median"] is None


def test_tables_count_events_for_each_fire_and_fires_for_each_event(monkeypatch):
    monkeypatch.setattr("chispa.config.EVAL_SIZE_CLASSES_HA", (10.0, 200.0))
    # The detections 0 and 1 are in the events 7 and 8. The two match fire 1 (100 hectares).
    found = {**FOUND, "event": np.array([7, 8, 9])}
    fires = two_fires([True, True])
    split = split_table(found, PAIRS, fires)
    small = split[0]
    assert (small["fires"], small["fires_found"], small["fires_in_one_event"]) == (1, 1, 0)
    # Fire 2 (300 hectares) has no detection. It does not count as an isolated fire.
    assert [row["fires_isolated"] for row in split] == [1, 0, 1]
    assert (small["events_per_fire_median"], small["events_per_fire_max"]) == (2.0, 2)
    low = event_table(found, PAIRS, fires, {7: "LOW", 8: "LOW", 9: "LOW"})[0]
    assert (low["events"], low["events_matched"], low["matched_share"]) == (3, 2, 0.6667)
    assert (low["events_on_one_fire"], low["fires_per_event_max"]) == (2, 1)


def test_purity_and_completeness():
    # Event 7 has three matches on fire 1 and one match on fire 2. Event 8 has one match on fire 2.
    found = {"event": np.array([7, 7, 7, 7, 8])}
    pairs = (np.arange(5), np.array([1, 1, 1, 2, 2]))
    fires = two_fires([False, False])
    by_level = {
        row["final_level"]: row for row in event_table(found, pairs, fires, {7: "HIGH", 8: "LOW"})
    }
    assert by_level["HIGH"]["purity"] == 0.75  # 3 of the 4 matches of event 7 are on fire 1
    assert by_level["LOW"]["purity"] == 1.0
    assert by_level["all"]["purity"] == 0.8  # 3 + 1 of 5 matches
    every = split_table(found, pairs, fires)[-1]
    assert (every["size_class_ha"], every["fires_found"]) == ("all", 2)
    assert every["completeness"] == 0.8  # fire 1: 3 of 3. Fire 2: 1 of 2.


def test_merge_gain_counts_fires_that_a_family_does_not_find_or_finds_later(monkeypatch):
    monkeypatch.setattr("chispa.config.EVAL_SIZE_CLASSES_HA", (10.0, 200.0))
    # Fire 1 (100 hectares): GOES at 1 h, VIIRS at 4 h. Fire 2 (300 hectares): only VIIRS.
    found = {
        "family": np.array(["abi", "viirs", "viirs"]),
        "available": np.array([3600.0, 14400.0, 0.0]),
    }
    pairs = (np.array([0, 1, 2]), np.array([1, 1, 2]))
    rows = {
        row["sensor_family"]: row
        for row in gain_table(found, pairs, two_fires([True, True]))
        if row["size_class_ha"] == "all"
    }
    goes, viirs = rows["abi"], rows["viirs"]
    assert (goes["fires_found_merged"], goes["fires_found_family"]) == (2, 1)
    assert (goes["fires_gained"], goes["gained_area_ha"], goes["fires_later"]) == (1, 300, 0)
    assert (viirs["fires_gained"], viirs["delay_fires"], viirs["fires_later"]) == (0, 2, 1)
    assert viirs["later_h_median"] == 3.0  # VIIRS is 3 hours after GOES for fire 1


def test_configuration_hash_covers_only_the_values_before_the_marker(monkeypatch, tmp_path):
    from chispa.evaluation import report

    path = tmp_path / "config.py"
    monkeypatch.setattr("chispa.config.__file__", str(path))
    path.write_text(f"LIMIT = 1\n{report.HASH_END}\nPATH = 'a'\n")
    first = report.config_hash()
    path.write_text(f"LIMIT = 1\n{report.HASH_END}\nPATH = 'b'\n")
    assert report.config_hash() == first
    path.write_text(f"LIMIT = 2\n{report.HASH_END}\nPATH = 'b'\n")
    assert report.config_hash() != first
