"""Tests of the burn check and of the image check, with cases small enough for paper."""

from datetime import UTC, datetime

import numpy as np

from chispa.evaluation import burn, candidates, images
from chispa.grid import Grid
from chispa.sources import monitor


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


def test_second_look_has_the_first_events_and_no_fire_boxes_with_no_id(monkeypatch):
    monkeypatch.setattr("chispa.config.IMAGE_NO_FIRE", 2)
    targets = targets_of("unmatched", 5) + targets_of("matched", 4) + targets_of("no fire", 4)
    first_key = [{"chip": 1, "id": "unmatched0"}, {"chip": 2, "id": "matched3"}]
    sample, key = images.draw_second(targets, first_key)
    assert sorted(row["id"] for row in key) == ["matched3", "no fire0", "no fire1", "unmatched0"]
    # The id of a no-fire box shows its group. Thus the sample of the person has no id.
    assert all(name not in row for row in sample for name in ("id", "group"))
    assert images.draw_second(targets, first_key) == (sample, key)


def test_second_look_with_no_first_look_takes_the_start_of_each_group(monkeypatch):
    monkeypatch.setattr(
        "chispa.config.IMAGE_TEST_SAMPLE", {"unmatched": 2, "matched": 1, "no fire": 1}
    )
    targets = targets_of("unmatched", 5) + targets_of("matched", 4) + targets_of("no fire", 4)
    sample, key = images.draw_second(targets, [])
    assert sorted(row["id"] for row in key) == ["matched0", "no fire0", "unmatched0", "unmatched1"]
    assert all("id" not in row for row in sample)


def test_second_look_counts_the_no_fire_boxes_as_their_own_group():
    answers = [("7", "unmatched", "burned"), ("box1", "no fire", "not burned")]
    unmatched, no_fire = images.count(answers)
    assert (no_fire["group"], no_fire["sample"], no_fire["not_burned"]) == ("boxes, no fire", 1, 1)


def test_pictures_are_the_last_clear_view_before_and_two_clear_views_after(monkeypatch):
    monkeypatch.setattr("chispa.config.BURN_DAYS", 30)
    monkeypatch.setattr("chispa.config.IMAGE_MIN_CLEAR", 0.8)
    monkeypatch.setattr("chispa.config.IMAGE_LATER_MIN_DAYS", 5)
    monkeypatch.setattr("chispa.config.IMAGE_LATER_DAYS", 60)
    first, last = datetime(2024, 8, 10, 17, tzinfo=UTC), datetime(2024, 8, 11, 5, tzinfo=UTC)

    def view(name, month, day, share):
        return name, datetime(2024, month, day, 14, tzinfo=UTC), share

    views = [
        view("old", 7, 1, 1.0),  # More than 30 days before the event.
        view("before", 7, 31, 0.9),
        view("cloud before", 8, 5, 0.5),  # Nearer to the event, with cloud on the box.
        view("day of the fire", 8, 10, 1.0),  # Not before the event, and not after it.
        view("cloud after", 8, 15, 0.2),
        view("after", 8, 20, 0.95),
        view("too near", 8, 22, 1.0),  # Less than 5 days after the picture after.
        view("later", 8, 25, 0.85),
    ]
    chosen = images.choose_views(views, first, last)
    assert [chosen[name][0] for name in images.VIEWS] == ["before", "after", "later"]
    # With no clear view after the event, the chip has only the picture before.
    chosen = images.choose_views(views[:5], first, last)
    assert (chosen["before"][0], chosen["after"], chosen["later"]) == ("before", None, None)


def test_monthly_map_reads_the_months_of_an_event_and_the_month_after(monkeypatch):
    monkeypatch.setattr("chispa.config.MONITOR_MONTHS_AFTER", 1)
    first, last = datetime(2024, 11, 28, tzinfo=UTC), datetime(2024, 12, 2, tzinfo=UTC)
    assert monitor.month_names(first, last) == ["brazil-2024-11", "brazil-2024-12", "brazil-2025-1"]


def test_candidate_has_no_answer_with_no_clear_view_or_no_radar_scene(monkeypatch):
    monkeypatch.setattr("chispa.config.BURN_MIN_CLEAR", 0.5)
    row = {"clear_share": "0.2", "scenes": "0", "0.2": "50", "VH/2.0": "", "monitor": "12.5"}
    assert candidates.answer(row, "box rule", "0.2", 10.0) is None
    assert candidates.answer(row, "radar VH", "VH/2.0", 10.0) is None
    assert candidates.answer(row, "monitor", "monitor", 10.0) is True
    assert candidates.answer({**row, "clear_share": "0.9"}, "box rule", "0.2", 100.0) is False


def test_candidate_table_gives_the_difference_and_marks_the_best_setting(monkeypatch):
    monkeypatch.setattr("chispa.config.BURN_DNBR_STEPS", (0.2,))
    monkeypatch.setattr("chispa.config.BURN_DARK_STEPS", (0.2,))
    monkeypatch.setattr("chispa.config.BURN_NBR2_STEPS", ())
    monkeypatch.setattr("chispa.config.RADAR_DB_STEPS", (2.0,))
    monkeypatch.setattr("chispa.config.BURN_HA_STEPS", (1.0, 10.0))
    monkeypatch.setattr("chispa.config.BURN_MIN_CLEAR", 0.5)
    targets = [
        {"id": n, "group": group}
        for n, group in enumerate(("matched", "matched", "no fire", "no fire"))
    ]

    def row(number, plain, dark):
        radar = {"scenes": 2, "VV/2.0": 0, "VH/2.0": 0, "monitor": 0}
        return {"id": str(number), "clear_share": 1.0, "0.2": plain, "0.2/0.2": dark, **radar}

    # At 1 hectare the box rule calls each box burned. The dark rule calls only the two fires.
    measures = [row(0, 30, 30), row(1, 12, 12), row(2, 5, 0), row(3, 20, 0)]
    monkeypatch.setattr("chispa.config.BURN_CANDIDATES", {"dark rule": ("0.2/0.2", 10.0)})
    rows = candidates.table(targets, measures, all_settings=True)
    by_name = {(r["candidate"], r["min_ha"]): r for r in rows}
    plain, dark = by_name[("box rule", 1.0)], by_name[("dark rule", 1.0)]
    assert (plain["found_share"], plain["no_fire_share"], plain["difference"]) == (1.0, 1.0, 0.0)
    assert (dark["found_share"], dark["no_fire_share"], dark["difference"]) == (1.0, 0.0, 1.0)
    assert by_name[("box rule", 10.0)]["difference"] == 0.5  # 2 of 2 fires, 1 of 2 no-fire boxes.
    assert (plain["best"], by_name[("box rule", 10.0)]["best"], dark["best"]) == ("", "yes", "yes")
    # A different year has only the setting of the configuration.
    frozen = candidates.table(targets, measures, all_settings=False)
    assert [(r["candidate"], r["key"], r["min_ha"]) for r in frozen] == [
        ("dark rule", "0.2/0.2", 10.0)
    ]


def test_candidate_against_a_person_counts_only_clear_answers_and_blind_events(monkeypatch):
    monkeypatch.setattr("chispa.config.BURN_MIN_CLEAR", 0.5)
    monkeypatch.setattr("chispa.config.BURN_CANDIDATES", {"box rule": ("0.3", 10.0)})
    monkeypatch.setattr("chispa.config.IMAGE_NOT_BLIND", ("9",))

    def row(number, clear_share, hectares):
        return {"id": str(number), "clear_share": clear_share, "scenes": 0, "0.3": hectares}

    measures = [row(1, 1.0, 50), row(2, 1.0, 0), row(3, 1.0, 40), row(4, 1.0, 0), row(5, 0.1, 90)]
    measures += [row(6, 1.0, 90), row(9, 1.0, 90)]
    answers = [
        ("1", "matched", "burned"),  # The rule finds it.
        ("2", "unmatched", "burned"),  # The rule does not find it.
        ("3", "no fire", "not burned"),  # The rule calls it burned.
        ("4", "no fire", "not burned"),
        ("5", "unmatched", "burned"),  # The rule has no clear view: no answer.
        ("6", "unmatched", "cannot tell"),
        ("9", "matched", "burned"),  # The person saw an opinion on this event.
    ]
    (found,) = candidates.person_table(answers, measures, apart=set())
    assert (found["chips"], found["person_burned"], found["found"]) == (4, 2, 1)
    assert (found["person_not_burned"], found["called_burned"]) == (2, 1)
    assert (found["agree"], found["agree_share"]) == (2, 0.5)
    # A chip where the person used the later picture is not in the comparison. The table counts it.
    (found,) = candidates.person_table(answers, measures, apart={"2"})
    assert (found["chips"], found["person_burned"], found["later_only"]) == (3, 1, 1)


def test_best_setting_of_two_equal_differences_is_the_smaller_area(monkeypatch):
    monkeypatch.setattr("chispa.config.BURN_DNBR_STEPS", (0.2, 0.3))
    monkeypatch.setattr("chispa.config.BURN_DARK_STEPS", ())
    monkeypatch.setattr("chispa.config.BURN_NBR2_STEPS", ())
    monkeypatch.setattr("chispa.config.RADAR_DB_STEPS", ())
    monkeypatch.setattr("chispa.config.BURN_HA_STEPS", (10.0, 25.0))
    monkeypatch.setattr("chispa.config.BURN_MIN_CLEAR", 0.5)
    monkeypatch.setattr("chispa.config.BURN_CANDIDATES", {})
    targets = [{"id": n, "group": group} for n, group in enumerate(("matched", "no fire"))]
    # The fire has 30 hectares at step 0.2 and 12 at step 0.3. The no-fire box has 12 and 0.
    measures = [
        {"id": "0", "clear_share": 1.0, "scenes": 0, "0.2": 30, "0.3": 12, "monitor": 0},
        {"id": "1", "clear_share": 1.0, "scenes": 0, "0.2": 12, "0.3": 0, "monitor": 0},
    ]
    rows = candidates.table(targets, measures, all_settings=True)
    best = [(r["key"], r["min_ha"]) for r in rows if r["candidate"] == "box rule" and r["best"]]
    # Step 0.2 with 25 hectares and step 0.3 with 10 hectares have a difference of 1.0.
    assert best == [("0.3", 10.0)]


def test_measures_of_different_settings_stop_a_run(tmp_path, monkeypatch):
    path = tmp_path / "measures.csv"
    path.write_text("id,settings,clear_share\n7,old-mark,1.0\n")
    try:
        candidates.measure([{"id": "7"}], path)
    except RuntimeError as error:
        assert "Delete it" in str(error)
    else:
        raise AssertionError("A file of different settings must stop the run.")
