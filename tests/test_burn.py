"""Tests of the burn check and of the image check, with cases small enough for paper."""

import numpy as np

from chispa.evaluation import burn, images
from chispa.grid import Grid


def test_high_events_go_to_two_groups_by_their_match():
    detections = {"event": np.array([1, 1, 2, 3])}
    pairs = (np.array([0]), np.array([7]))  # Only the first detection matches a fire.
    final_level = {1: "HIGH", 2: "HIGH", 3: "LOW"}
    assert burn.groups(detections, pairs, final_level) == {"unmatched": [2], "matched": [1]}


def test_sequence_is_the_same_each_time_and_has_each_event():
    events = list(range(100, 120))
    assert burn.order(events, "matched") == burn.order(events[::-1], "matched")
    assert sorted(burn.order(events, "matched")) == events
    assert burn.order(events, "matched") != burn.order(events, "unmatched")


def test_box_adds_the_margin_on_each_side(monkeypatch):
    monkeypatch.setattr("chispa.config.BURN_MARGIN_M", 110_574.0)  # one degree of latitude
    south, west, north, east = burn.with_margin(-1.0, 10.0, 1.0, 11.0)
    assert (round(south, 6), round(north, 6)) == (-2.0, 2.0)
    assert round(east - 11.0, 3) == round(10.0 - west, 3) == 0.993


def test_box_with_a_fire_pixel_or_a_detection_is_not_free(monkeypatch):
    monkeypatch.setattr("chispa.config.BURN_MARGIN_M", 0.0)
    grid = Grid(west=0.0, north=10.0, pixel_deg=1.0, width=10, height=10)
    numbers = np.zeros((10, 10), dtype=int)
    numbers[2, 2] = 5  # A fire pixel at latitude 7 to 8, longitude 2 to 3.
    detections = {"lat": np.array([4.5]), "lon": np.array([6.5])}
    in_time = np.array([True])
    assert not burn._is_free((7.2, 2.2, 7.8, 2.8), detections, in_time, numbers, grid)
    assert not burn._is_free((4.2, 6.2, 4.8, 6.8), detections, in_time, numbers, grid)
    assert burn._is_free((4.2, 6.2, 4.8, 6.8), detections, np.array([False]), numbers, grid)
    assert burn._is_free((0.2, 0.2, 0.8, 0.8), detections, in_time, numbers, grid)


def measure_row(event, clear_share, hectares):
    return {"id": str(event), "clear_share": str(clear_share), "0.1": str(hectares), "0.2": "0"}


def test_rule_gives_no_answer_for_a_view_that_is_not_clear(monkeypatch):
    monkeypatch.setattr("chispa.config.BURN_MIN_CLEAR", 0.5)
    assert burn.is_burned(measure_row(1, 0.9, 3.0), 0.1, 1.0) is True
    assert burn.is_burned(measure_row(1, 0.9, 3.0), 0.1, 10.0) is False
    assert burn.is_burned(measure_row(1, 0.4, 3.0), 0.1, 1.0) is None


def test_table_counts_the_burned_boxes_of_each_group(monkeypatch):
    monkeypatch.setattr("chispa.config.BURN_DNBR_STEPS", (0.1, 0.2))
    monkeypatch.setattr("chispa.config.BURN_HA_STEPS", (1.0,))
    monkeypatch.setattr("chispa.config.BURN_DNBR_MIN", 0.1)
    monkeypatch.setattr("chispa.config.BURN_HA_MIN", 1.0)
    monkeypatch.setattr("chispa.config.BURN_MIN_CLEAR", 0.5)
    targets = [
        {"id": 1, "group": "unmatched", "events_in_group": 40, "map_in_box": "yes"},
        {"id": 2, "group": "unmatched", "events_in_group": 40, "map_in_box": "no"},
        {"id": 3, "group": "unmatched", "events_in_group": 40, "map_in_box": "no"},
        {"id": "box1", "group": "no fire", "events_in_group": "", "map_in_box": "no"},
    ]
    measures = [measure_row(1, 1.0, 5.0), measure_row(2, 1.0, 0.0), measure_row(3, 0.1, 5.0)]
    measures.append(measure_row("box1", 1.0, 0.0))
    everything, no_map, matched, boxes = burn.table(targets, measures, all_pairs=False)
    assert (everything["events"], everything["sample"], everything["clear"]) == (40, 3, 2)
    assert (everything["burned"], everything["burned_share"], everything["chosen"]) == (
        1,
        0.5,
        "yes",
    )
    assert (no_map["sample"], no_map["clear"], no_map["burned"]) == (2, 1, 0)
    assert (matched["sample"], matched["burned_share"]) == (0, None)
    assert (boxes["group"], boxes["clear"], boxes["burned"]) == ("boxes, no fire", 1, 0)
    assert len(burn.table(targets, measures, all_pairs=True)) == 8


def test_rule_quality_on_the_two_reference_groups(monkeypatch):
    monkeypatch.setattr("chispa.config.BURN_DNBR_MIN", 0.1)
    monkeypatch.setattr("chispa.config.BURN_HA_MIN", 1.0)
    monkeypatch.setattr("chispa.config.BURN_MIN_CLEAR", 0.5)
    targets = [{"id": n, "group": "matched"} for n in (1, 2, 3, 4)]
    targets += [{"id": n, "group": "no fire"} for n in (5, 6)]
    burned = {1: 5.0, 2: 5.0, 3: 5.0, 4: 0.0, 5: 5.0, 6: 0.0}
    measures = [measure_row(event, 1.0, hectares) for event, hectares in burned.items()]
    (row,) = burn.rule_table(targets, measures)
    # 3 of 4 fires found. 1 of 2 boxes called burned. Precision 3 / 4. F1 = 6 / (6 + 1 + 1).
    assert (row["recall"], row["false_share"], row["precision"], row["f1"]) == (
        0.75,
        0.5,
        0.75,
        0.75,
    )


def targets_of(group, count):
    return [{"id": f"{group}{n}", "group": group, "events_in_group": 99} for n in range(count)]


def test_person_sample_is_the_start_of_each_group_and_hides_the_group(monkeypatch):
    monkeypatch.setattr("chispa.config.IMAGE_SAMPLE", 3)
    monkeypatch.setattr("chispa.config.IMAGE_CONTROL", 2)
    targets = targets_of("unmatched", 5) + targets_of("matched", 4) + targets_of("no fire", 4)
    sample, key = images.draw(targets)
    assert [row["chip"] for row in sample] == [1, 2, 3, 4, 5]
    assert all("group" not in name for row in sample for name in row)
    wanted = ["matched0", "matched1", "unmatched0", "unmatched1", "unmatched2"]
    assert sorted(row["id"] for row in key) == wanted
    assert images.draw(targets) == (sample, key)


def test_person_answers_are_counted_and_compared_with_the_rule(monkeypatch):
    monkeypatch.setattr("chispa.config.BURN_DNBR_MIN", 0.1)
    monkeypatch.setattr("chispa.config.BURN_HA_MIN", 1.0)
    monkeypatch.setattr("chispa.config.BURN_MIN_CLEAR", 0.5)
    answers = [
        ("1", "unmatched", "burned"),
        ("2", "unmatched", "not burned"),
        ("3", "unmatched", "cannot tell"),
        ("4", "unmatched", ""),
        ("5", "matched", "burned"),
    ]
    unmatched, matched = images.count(answers)
    assert (unmatched["sample"], unmatched["burned"], unmatched["not_burned"]) == (4, 1, 1)
    assert (unmatched["cannot_tell"], unmatched["no_answer"], unmatched["burned_share"]) == (
        1,
        1,
        0.5,
    )
    assert (matched["sample"], matched["burned_share"]) == (1, 1.0)
    measures = [measure_row(1, 1.0, 5.0), measure_row(2, 1.0, 5.0), measure_row(3, 0.1, 0.0)]
    measures.append(measure_row(5, 1.0, 0.0))
    burned, not_burned, cannot_tell = images.agreement(answers, measures)
    assert (burned["chips"], burned["rule_burned"], burned["rule_not_burned"]) == (2, 1, 1)
    assert (not_burned["chips"], not_burned["rule_burned"]) == (1, 1)
    assert (cannot_tell["chips"], cannot_tell["rule_no_clear_view"]) == (1, 1)
