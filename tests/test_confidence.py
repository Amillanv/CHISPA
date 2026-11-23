"""Tests of the confidence model and of its tables, with cases small enough for paper."""

import numpy as np

from chispa import confidence
from chispa.evaluation.confidence import (
    activity,
    as_table,
    detection_fires,
    event_fires,
    level_rates,
    near_count,
    result_tables,
    separation,
    weight_table,
)


def found(**changes):
    facts = {
        "detections": 1,
        "max_frp_mw": None,
        "extent_km": 0.0,
        "advance_m": None,
        "cover": "forest",
        "people_near": 0.0,
        "protected_km": 0.0,
        "indigenous_km": 0.0,
    }
    return facts | changes


def seen(**changes):
    return {
        "families": {"viirs"},
        "has_high": False,
        "day": 1,
        "local_hour": 12.0,
        "near": 0,
    } | changes


def test_inputs_come_from_the_facts_and_from_what_the_detections_say():
    values = confidence.inputs(found(), seen())
    assert set(values) == set(confidence.INPUTS + confidence.LATER_INPUTS)
    assert (values["has_viirs"], values["has_abi"], values["families"]) == (1.0, 0.0, 1.0)
    assert (values["on_forest"], values["on_pasture"]) == (1.0, 0.0)
    assert (values["no_power"], values["power_log"], values["night"]) == (1.0, 0.0, 0.0)
    assert round(values["detections_log"], 4) == round(float(np.log(2)), 4)


def test_inputs_for_a_night_detection_with_fire_power_and_an_advance():
    values = confidence.inputs(
        found(max_frp_mw=9.0, advance_m=1500.0, cover=None),
        seen(local_hour=22.0, has_high=True, near=9),
    )
    assert round(values["near_log"], 4) == round(float(np.log(10)), 4)
    assert (values["night"], values["has_high"], values["no_power"]) == (1.0, 1.0, 0.0)
    assert (values["has_advance"], values["on_forest"]) == (1.0, 0.0)
    assert round(values["power_log"], 4) == round(float(np.log(10)), 4)


def test_model_gives_a_higher_probability_where_the_input_goes_with_a_match(monkeypatch):
    monkeypatch.setattr("chispa.config.CONFIDENCE_PENALTY", 0.001)
    # One input. A match is more frequent where the input is 1.
    table = np.array([[0.0]] * 10 + [[1.0]] * 10)
    matched = np.array([0.0] * 8 + [1.0] * 2 + [0.0] * 2 + [1.0] * 8)
    model = confidence.fit(table, matched, ("x",))
    low, high = confidence.probability(model, np.array([[0.0], [1.0]]))
    assert model["weights"][0] > 0
    assert (round(float(low), 1), round(float(high), 1)) == (0.2, 0.8)


def test_separation_is_the_share_of_pairs_in_the_correct_sequence():
    values = np.array([0.9, 0.8, 0.3, 0.1])
    assert separation(values, np.array([1.0, 1.0, 0.0, 0.0])) == 1.0
    assert separation(values, np.array([1.0, 0.0, 1.0, 0.0])) == 0.75
    assert separation(np.array([1.0, 1.0, 1.0, 1.0]), np.array([1.0, 0.0, 1.0, 0.0])) == 0.5


def test_tables_compare_the_probability_with_the_level():
    model = {"inputs": ["x"], "mean": [0.0], "spread": [1.0], "start": 0.0, "weights": [2.0]}
    model |= {"base_rate": 0.6, "level_rates": [0.75, 0.0, 0.6]}
    rows = [
        {
            "inputs": {"x": value},
            "level": level,
            "matched": matched,
            "fires": frozenset(),
            "own_fires": frozenset(),
        }
        for value, level, matched in (
            (-2, 0, False),
            (-1, 1, False),
            (0, 0, True),
            (1, 0, True),
            (2, 0, True),
        )
    ]
    tables = result_tables({"0": rows, "24": rows}, {"0": model, "24": model})
    by_measure = {(row["moment_h"], row["measure"]): row for row in tables["confidence"]}
    assert by_measure[("0", "probability")]["match_separation"] == 1.0
    assert by_measure[("0", "level")]["match_separation"] == 0.25
    assert by_measure[("0", "level")]["alerts_matched"] == 3
    # The level gives 0.75 to four events (3 match) and 0 to one event with no match.
    assert by_measure[("0", "level")]["brier"] == round((3 * 0.25**2 + 0.75**2) / 5, 4)
    assert (
        by_measure[("0", "probability")]["brier_skill"] > by_measure[("0", "level")]["brier_skill"]
    )
    assert by_measure[("0", "probability")]["top_tenth"] == 0
    assert by_measure[("0", "probability")]["top_tenth_fires"] == 0
    fifths = [row for row in tables["confidence_calibration"] if row["moment_h"] == "0"]
    assert [row["matched_share"] for row in fifths] == [0.0, 0.0, 1.0, 1.0, 1.0]
    # The model gave 0.5 to the event of the third group, and that event matched: 1 / 0.5.
    assert fifths[2]["observed_to_predicted"] == 2.0
    assert as_table(rows, ("x",))[0].shape == (5, 1)
    assert weight_table({"0": model, "24": model})[0] == {
        "moment_h": "0",
        "input": "x",
        "weight": 2.0,
    }


def test_activity_counts_only_the_days_before_and_the_cells_around(monkeypatch):
    monkeypatch.setattr("chispa.config.PANTANAL_BOX", (0.0, 0.0, 1.0, 1.0))
    monkeypatch.setattr("chispa.config.CONFIDENCE_NEAR_CELL_DEG", 0.1)
    monkeypatch.setattr("chispa.config.CONFIDENCE_NEAR_DAYS", 2)
    day = 86_400.0
    detections = {
        # Day 0: far in time. Day 1 and day 2: near. Day 3: the same day. Day 2: far in space.
        "available": np.array([0.0, day, 2 * day, 3 * day, 2 * day]),
        "lat": np.array([0.55, 0.55, 0.65, 0.55, 0.95]),
        "lon": np.array([0.55, 0.55, 0.45, 0.55, 0.05]),
    }
    counts, place = activity(detections)
    assert near_count(counts, place, 3 * day + 100, 0.55, 0.55) == 2
    assert near_count(counts, place, 0.0, 0.55, 0.55) == 0


def test_level_with_no_event_gets_the_share_of_all_events():
    rows = [
        {"level": 0, "matched": True},
        {"level": 0, "matched": False},
        {"level": 2, "matched": True},
    ]
    assert level_rates(rows, 0.4) == [0.5, 0.4, 1.0]


def test_event_gets_each_counted_fire_that_it_matches():
    detections = {"event": np.array([1, 1, 2, 3])}
    pairs = (np.array([0, 1, 1, 2, 3]), np.array([5, 5, 6, 5, 9]))
    fires = {"counted": np.array([False] * 5 + [True, True, False, False, False])}
    assert event_fires(detections, pairs, fires) == {1: frozenset({5, 6}), 2: frozenset({5})}


def test_top_tenth_counts_the_different_fires():
    model = {"inputs": ["x"], "mean": [0.0], "spread": [1.0], "start": 0.0, "weights": [1.0]}
    model |= {"base_rate": 0.5, "level_rates": [0.5, 0.5, 0.5]}
    # 20 events. The two events with the largest values match the same fire.
    rows = [
        {
            "inputs": {"x": float(n)},
            "level": 0,
            "matched": n >= 18,
            "fires": frozenset({7} if n >= 18 else ()),
            "own_fires": frozenset({7} if n == 19 else ()),
        }
        for n in range(20)
    ]
    tables = result_tables({"0": rows, "24": rows}, {"0": model, "24": model})
    first = tables["confidence"][0]
    assert (first["top_tenth"], first["top_tenth_matched"], first["top_tenth_fires"]) == (2, 2, 1)
    assert first["top_tenth_own_fires"] == 1


def test_each_detection_gets_its_counted_fires():
    detections = {"event": np.array([1, 1, 2])}
    pairs = (np.array([2, 0, 0, 1]), np.array([6, 5, 6, 9]))  # Detection 0: fires 5 and 6.
    fires = {"counted": np.array([False] * 5 + [True, True, False, False, False])}
    first, fire = detection_fires(detections, pairs, fires)
    assert [fire[first[d] : first[d + 1]].tolist() for d in range(3)] == [[5, 6], [], [6]]
