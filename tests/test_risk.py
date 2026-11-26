"""Tests of the growth risk: the new fires, the size of an alert, the measures and the years."""

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from chispa.evaluation import risk_inputs, risk_run
from chispa.evaluation.risk import (
    all_alerts_table,
    average_precision,
    fit_models,
    group_table,
    key,
    measures,
    new_or_none,
    result_table,
    seen_first,
    sized_rows,
    weight_table,
)
from chispa.evaluation.risk_calibration import calibration_table, source_table
from chispa.evaluation.risk_rule import rule_table

SAMPLES = Path(__file__).parent / "samples"


@pytest.fixture(autouse=True)
def no_adopted_inputs(monkeypatch):
    """Each test gives its own inputs: the models then have no adopted input."""
    monkeypatch.setattr("chispa.evaluation.risk.ADOPTED", ())
    monkeypatch.setattr("chispa.evaluation.risk.REMOVED", ())


def test_alert_that_saw_a_fire_first_is_the_alert_of_its_first_detection():
    detections = {
        "issued": np.array([11, 12, 11, 13]),
        "available": np.array([100.0, 50.0, 50.0, 10.0]),
    }
    # Fire 5: detection 0 (time 100) and detection 1 (time 50). Fire 6: detections 1 and 2,
    # the two at time 50. Fire 7 is not a counted fire.
    pairs = (np.array([0, 1, 1, 2, 3]), np.array([5, 5, 6, 6, 7]))
    fires = {"counted": np.array([False] * 5 + [True, True, False])}
    assert seen_first(detections, pairs, fires) == {5: 12, 6: 11}


def test_alert_has_the_area_of_its_largest_new_fire_and_a_known_fire_has_a_mark():
    area_ha = np.array([0.0, 0.0, 0.0, 0.0, 0.0, 50.0, 2000.0, 300.0])
    first = {5: 1, 6: 1, 7: 2}
    rows = [
        {"alert": 1, "own_fires": frozenset({5})},  # It saw the fires 5 and 6 first.
        {"alert": 2, "own_fires": frozenset({7, 5})},  # On fire 5, which alert 1 saw first.
        {"alert": 3, "own_fires": frozenset()},  # No mapped fire.
        {"alert": 4, "own_fires": frozenset({6})},  # On fire 6: a known fire.
    ]
    sized = sized_rows(rows, first, area_ha)
    assert [row["known"] for row in sized] == [False, True, False, True]
    # Alert 1 saw the fire of 2000 hectares first, but at the moment it matches only fire 5.
    assert (sized[0]["size_ha"], sized[0]["seen_ha"]) == (2000.0, 50.0)
    assert (sized[1]["size_ha"], sized[1]["seen_ha"]) == (300.0, 300.0)
    assert [(row["alert"], row["size_ha"]) for row in new_or_none(sized)] == [(1, 2000.0), (3, 0.0)]


def test_measures_count_the_large_alerts_and_their_sequence(monkeypatch):
    monkeypatch.setattr("chispa.config.RISK_LARGEST_HA", 10000.0)
    # 10 alerts. The value is in the sequence of the sizes. Two alerts became large.
    size = np.array([0, 0, 0, 0, 0, 0, 50, 150, 1500, 20000], dtype=float)
    found = measures(np.arange(10, dtype=float), size, size, 1000.0)
    assert (found["alerts"], found["large"], found["base_rate"]) == (10, 2, 0.2)
    assert (found["auc"], found["auc_new_fire_alerts"], found["average_precision"]) == (
        1.0,
        1.0,
        1.0,
    )
    assert (found["top_tenth"], found["top_tenth_large"], found["new_fire_alerts"]) == (1, 1, 4)
    assert (found["precision_top_tenth"], found["recall_top_tenth"]) == (1.0, 0.5)
    assert (found["largest_alerts"], found["top_tenth_largest_alerts"]) == (1, 1)
    # A value that finds the alerts with a fire, and puts their sizes in the wrong sequence:
    # 2 large alerts against 8 others give 16 pairs, and 12 of them are in the correct sequence.
    wrong = np.array([0, 0, 0, 0, 0, 0, 9, 8, 7, 6], dtype=float)
    found = measures(wrong, size, size, 1000.0)
    assert (found["auc"], found["auc_new_fire_alerts"]) == (0.75, 0.0)
    # The two large alerts are at places 3 and 4: precision 1 of 3 and 2 of 4.
    assert found["average_precision"] == round((1 / 3 + 2 / 4) / 2, 4)


def test_size_at_the_moment_gives_its_own_count_and_auc(monkeypatch):
    monkeypatch.setattr("chispa.config.RISK_LARGEST_HA", 10000.0)
    # The alert with the largest value became large, but from a fire that it did not match
    # at the moment. With the size at the moment, only the third alert is large.
    size = np.array([0.0, 0.0, 2000.0, 3000.0])
    seen = np.array([0.0, 0.0, 2000.0, 50.0])
    found = measures(np.array([1.0, 2.0, 3.0, 4.0]), size, seen, 1000.0)
    assert (found["large"], found["auc"]) == (2, 1.0)
    assert (found["large_at_moment"], found["auc_at_moment"]) == (1, round(2 / 3, 4))


def test_average_precision_of_equal_values_is_the_base_rate():
    large = np.array([True, False, True, False])
    assert average_precision(np.array([3.0, 2.0, 1.0, 0.0]), large) == round((1 + 2 / 3) / 2, 4)
    assert average_precision(np.ones(4), large) == 0.5
    assert average_precision(np.ones(4), np.zeros(4, dtype=bool)) is None


def alert(x: float, size_ha: float, advance_m: float | None = None, **more) -> dict:
    row = {"inputs": {"x": x, "detections_log": -x}, "size_ha": size_ha, "advance_m": advance_m}
    row |= {"seen_ha": size_ha, "known": False, "own_fires": frozenset(), "alert": int(x)}
    return row | {"matched": size_ha > 0, "only_inpe_goes": False, "at": 0.0} | more


MODEL = {"inputs": ["x"], "mean": [0.0], "spread": [1.0], "start": 0.0, "weights": [1.0]}


def test_table_compares_the_growth_risk_with_each_baseline(monkeypatch):
    monkeypatch.setattr("chispa.config.RISK_LIMITS_HA", (100.0,))
    monkeypatch.setattr("chispa.config.RISK_LARGEST_HA", 10000.0)
    against = MODEL | {"weights": [-1.0]}
    # The largest fire is the only alert with a measured advance.
    rows = [alert(0, 0.0), alert(1, 0.0), alert(2, 150.0), alert(3, 20000.0, 900.0)]
    kept = {"0": rows, "24": rows}
    models = {key("0", 100.0): MODEL, key("24", 100.0): MODEL}
    table = result_table(kept, models, {"0": against, "24": against})
    found = {(row["moment_h"], row["value"]): row["auc"] for row in table}
    assert found[("0", "growth_risk")] == 1.0
    assert found[("0", "confidence")] == 0.0
    assert found[("0", "detections")] == 0.0
    # The alert with the advance is before the two alerts that are not large: 2 pairs of 4.
    # For the other large alert, each value is equal: a half for its 2 pairs.
    assert found[("24", "persistence")] == 0.75
    assert ("0", "persistence") not in found


def test_all_alerts_table_counts_the_different_fires_that_the_top_tenth_reaches(monkeypatch):
    monkeypatch.setattr("chispa.config.RISK_LIMITS_HA", (100.0,))
    area_ha = np.array([0.0, 500.0, 900.0, 20.0])
    # 20 alerts. The two with the largest x are on fire 1: a known fire for the last alert.
    # The alert with the smallest x is on fire 2, and it is a large alert of the main table.
    rows = [alert(float(n), 0.0) for n in range(20)]
    rows[19] |= {"own_fires": frozenset({1, 3}), "known": True, "size_ha": 0.0}
    rows[18] |= {"own_fires": frozenset({1}), "size_ha": 500.0}
    rows[0] |= {"own_fires": frozenset({2}), "size_ha": 900.0}
    sized = {"0": rows, "24": rows}
    models = {key("0", 100.0): MODEL, key("24", 100.0): MODEL}
    against = MODEL | {"weights": [-1.0]}
    table = all_alerts_table(sized, area_ha, models, {"0": against, "24": against})
    found = {(row["moment_h"], row["value"]): row for row in table}
    first = found[("0", "growth_risk")]
    assert (first["alerts"], first["known_fire_alerts"], first["top_tenth"]) == (20, 1, 2)
    # The top tenth is the alerts 19 and 18: one known fire alert, and one fire of 2 in reach.
    assert (first["top_tenth_known_fire_alerts"], first["large_fires"]) == (1, 2)
    assert (first["top_tenth_large_fires"], first["large"], first["top_tenth_large"]) == (1, 2, 1)
    # The confidence has the other sequence: its top tenth is the alerts 0 and 1.
    other = found[("0", "confidence")]
    assert (other["top_tenth_large_fires"], other["top_tenth_large"]) == (1, 1)
    assert other["top_tenth_known_fire_alerts"] == 0


def test_models_have_one_weight_table_and_one_model_for_each_moment_and_limit(monkeypatch):
    monkeypatch.setattr("chispa.config.RISK_LIMITS_HA", (100.0, 1000.0))
    monkeypatch.setattr("chispa.evaluation.risk.names_of", lambda moment: ("x",))
    rows = [alert(float(n % 2), 2000.0 * (n % 2)) for n in range(20)]
    models = fit_models({"0": rows, "24": rows})
    assert set(models) == {"0h_100ha", "0h_1000ha", "24h_100ha", "24h_1000ha"}
    assert models["0h_1000ha"]["weights"][0] > 0
    assert weight_table(models)[0]["model"] == "0h_100ha"


def test_group_table_counts_the_alerts_of_each_group(monkeypatch):
    monkeypatch.setattr("chispa.config.EVAL_SIZE_CLASSES_HA", (10.0, 100.0))
    fires = {"area_ha": np.array([0.0, 5.0, 50.0, 60.0, 500.0])}
    kept = [alert(0, 0.0), alert(1, 50.0), alert(2, 500.0)]
    table = group_table({"0": kept + [alert(3, 0.0, known=True)], "24": kept}, fires)
    found = {(row["moment_h"], row["group"]): (row["alerts"], row["fires"]) for row in table}
    assert found[("0", "all alerts")] == (4, None)
    assert found[("0", "known fire: left out")] == (1, None)
    assert found[("24", "known fire: left out")] == (0, None)
    assert found[("0", "no mapped fire")] == (1, None)
    # Two fires are in the class of 10 to 100 hectares, and one of them is a new fire of an alert.
    assert found[("0", "new fire, 10 to 100 hectares")] == (1, 2)
    assert found[("0", "new fire, 100 to inf hectares")] == (1, 1)


def test_tables_of_a_year_come_from_models_of_the_other_years(tmp_path, monkeypatch):
    monkeypatch.setattr("chispa.config.YEAR_ROLES", {2001: "a", 2002: "b", 2003: "c"})
    monkeypatch.setattr("chispa.config.RISK_LIMITS_HA", (100.0,))
    monkeypatch.setattr("chispa.config.RESULTS_DIR", tmp_path)
    monkeypatch.setattr("chispa.evaluation.risk.names_of", lambda moment: ("x",))
    folder = tmp_path / "2023" / "confidence"
    folder.mkdir(parents=True)
    (folder / "model.json").write_text(json.dumps({"0": MODEL, "24": MODEL}))
    # In 2001 and 2002 a large x is a large fire. In 2003 a small x is a large fire.
    usual = [alert(float(n % 2), 500.0 * (n % 2)) for n in range(20)]
    other = [alert(float(n % 2), 500.0 * (1 - n % 2)) for n in range(20)]
    # An alert on a known fire gives the models no row: these say the opposite of the others.
    usual = usual + [alert(0.0, 500.0, known=True)] * 40
    parts = {year: {"rows": {"0": usual, "24": usual}} for year in (2001, 2002)}
    parts[2003] = {"rows": {"0": other, "24": other}}
    for part in parts.values():
        part |= {"area_ha": np.zeros(1), "alerts": []}
    monkeypatch.setattr(risk_run, "year_parts", lambda year, store, raw: parts[year])
    # The second set of inputs has `detections_log`: for these rows it is x with the other sign.
    sets = {"inputs now": ((), ()), "with more": (("detections_log",), ())}
    monkeypatch.setattr(risk_run, "INPUT_SETS", sets)
    tables = risk_run.risk_tables(tmp_path / "store", tmp_path)
    assert set(tables) == {2001, 2002, 2003}
    names = {"risk", "risk_all_alerts", "risk_calibration", "risk_alerts", "risk_weights"}
    names |= {"risk_inputs", "risk_fire"}
    sets = {(row["inputs"], row["moment_h"]): row for row in tables[2003]["risk_inputs"]}
    assert set(sets) == {
        ("inputs now", "0"),
        ("inputs now", "24"),
        ("with more", "0"),
        ("with more", "24"),
    }
    # The table of 2003 has the level after the recalibration: 2003 is the one scored year.
    assert sets[("inputs now", "0")]["recalibrated_observed_to_expected"] is not None
    assert tables[2001]["risk_inputs"][0]["recalibrated_observed_to_expected"] is None
    assert tables[2001]["risk_inputs"][0]["alerts"] == 20
    assert set(tables[2001]) == names
    earlier = {"risk_earlier", "risk_calibration_earlier", "risk_level_sources"}
    assert set(tables[2002]) == names | earlier | {"risk_fire_calibration"}
    # The table of the rule is for all years together: it is with the newest year.
    # Only 2003 has two training years: it is the one scored year of the recalibration.
    scored = {"risk_recalibrated", "risk_classes", "risk_percentage"}
    assert set(tables[2003]) == set(tables[2002]) | {"risk_input_rule"} | scored
    assert {row["inputs"] for row in tables[2003]["risk_input_rule"]} == {"with more"}
    # With the earlier years only, 2002 has the weights of 2001: the same form, thus correct.
    assert tables[2002]["risk_earlier"][0]["auc"] == 1.0
    assert tables[2003]["risk_earlier"][0]["auc"] == 0.0
    # The models of 2003 learned only the two usual years: they are wrong for 2003.
    assert tables[2003]["risk"][0]["auc"] == 0.0
    # The models of 2001 learned from 2002 and 2003, which disagree: the weight is near zero.
    assert abs(tables[2001]["risk_weights"][0]["weight"]) < 0.01
    assert tables[2001]["risk"][0]["alerts"] == 20


def test_calibration_gives_the_brier_skill_and_the_observed_against_the_expected(monkeypatch):
    monkeypatch.setattr("chispa.config.RISK_LIMITS_HA", (100.0, 1000.0))
    monkeypatch.setattr("chispa.evaluation.risk_calibration.TENTHS", 2)
    # A model with no weight gives each alert its start value: 0 is a probability of 0.5.
    model = MODEL | {"weights": [0.0], "base_rate": 0.5}
    rows = [alert(0, 0.0), alert(1, 0.0), alert(2, 150.0), alert(3, 2000.0)]
    models = {key(moment, limit): model for moment in ("0", "24") for limit in (100.0, 1000.0)}
    table = calibration_table({"0": rows, "24": rows}, models)
    found = {(row["limit_ha"], row["group"]): row for row in table if row["moment_h"] == "0"}
    first = found[(100.0, "all")]
    # 4 alerts with a probability of 0.5: 2 expected, and 2 became 100 hectares or more.
    assert (first["expected_large"], first["large"], first["observed_to_expected"]) == (2.0, 2, 1.0)
    # Each error is 0.5: the Brier score is 0.25, the same as that of the constant 0.5.
    assert (first["brier"], first["brier_skill"], first["above_lower_limit"]) == (0.25, 0.0, None)
    # For 1000 hectares 1 of 4 became large: the values are too high by a factor of 2.
    assert found[(1000.0, "all")]["observed_to_expected"] == 0.5
    assert found[(1000.0, "all")]["above_lower_limit"] == 0
    assert (found[(100.0, "2")]["alerts"], found[(100.0, "2")]["large"]) == (2, 2)


def test_brier_skill_has_no_value_when_the_constant_has_no_error(monkeypatch):
    monkeypatch.setattr("chispa.config.RISK_LIMITS_HA", (100.0,))
    # No large alert in the training years (base rate 0) and none in the year.
    model = MODEL | {"base_rate": 0.0}
    rows = [alert(0, 0.0), alert(1, 0.0)]
    models = {key("0", 100.0): model, key("24", 100.0): model}
    first = calibration_table({"0": rows, "24": rows}, models)[0]
    assert (first["group"], first["brier_skill"], first["large"]) == ("all", None, 0)


def test_calibration_group_with_no_alert_has_no_mean(monkeypatch):
    monkeypatch.setattr("chispa.config.RISK_LIMITS_HA", (100.0,))
    # 3 alerts and the default ten groups: seven groups have no alert.
    model = MODEL | {"base_rate": 0.5}
    rows = [alert(0, 0.0), alert(1, 150.0), alert(2, 150.0)]
    models = {key("0", 100.0): model, key("24", 100.0): model}
    table = calibration_table({"0": rows, "24": rows}, models)
    groups = [row for row in table if row["moment_h"] == "0" and row["group"] != "all"]
    assert len(groups) == 10
    empty = [row for row in groups if row["alerts"] == 0]
    assert len(empty) == 7
    assert all(row["probability_mean"] is None for row in empty)
    assert all(row["observed_to_expected"] is None for row in empty)


def test_dryness_of_an_alert_is_the_median_of_its_detections_with_a_value():
    # Three detections: 9 days and 0 mm, 3 days and 2 mm with no fire risk, and one with no row.
    dryness = np.array([[9.0, 0.0, 0.8], [3.0, 2.0, np.nan], [np.nan, np.nan, np.nan]])
    found = risk_inputs.dryness_inputs(dryness, np.array([0, 1, 2]))
    assert round(found["dry_days_log"], 4) == round(float(np.log(1 + 6.0)), 4)
    assert round(found["rain_mm_log"], 4) == round(float(np.log(1 + 1.0)), 4)
    assert (found["fire_risk"], found["no_dryness"], found["no_fire_risk"]) == (0.8, 0.0, 0.0)
    nothing = risk_inputs.dryness_inputs(dryness, np.array([2]))
    assert nothing == dict.fromkeys(("dry_days_log", "rain_mm_log", "fire_risk"), 0.0) | {
        "no_dryness": 1.0,
        "no_fire_risk": 1.0,
    }
    assert set(found) == set(risk_inputs.DRYNESS)


def test_detection_gets_the_dryness_of_its_row_in_the_archive_file(tmp_path):
    (tmp_path / "inpe").mkdir()
    shutil.copy(SAMPLES / "inpe_anual_sample.csv", tmp_path / "inpe" / "focos_mensal_br_201901.csv")
    # The second row of the sample: NPP-375 at 2019-01-01 17:36:00, 2 days with no rain, 1.2 mm.
    seconds = int(datetime(2019, 1, 1, 17, 36, tzinfo=UTC).timestamp())
    detections = {
        "source": np.array(["inpe", "firms", "inpe"]),
        "observed": np.array([seconds, seconds, seconds + 60]),
        "lat": np.array([-18.95416, -18.95416, -18.95416]),
        "lon": np.array([-57.27932, -57.27932, -57.27932]),
    }
    found = risk_inputs.dryness_of(detections, tmp_path, 2019)
    assert found[0].tolist() == [2.0, 1.2, 0.1]
    # A FIRMS detection has no row in an INPE file, and a different time finds no row.
    assert np.isnan(found[1]).all() and np.isnan(found[2]).all()


def test_models_can_have_more_inputs_and_fewer_inputs(monkeypatch):
    monkeypatch.setattr("chispa.config.RISK_LIMITS_HA", (100.0,))
    monkeypatch.setattr("chispa.evaluation.risk.names_of", lambda moment: ("x", "detections_log"))
    rows = [alert(float(n % 2), 2000.0 * (n % 2)) for n in range(20)]
    kept = {"0": rows, "24": rows}
    assert fit_models(kept)["0h_100ha"]["inputs"] == ["x", "detections_log"]
    assert fit_models(kept, remove=("x",))["0h_100ha"]["inputs"] == ["detections_log"]
    changed = fit_models(kept, add=("x",), remove=("x", "detections_log"))
    assert changed["24h_100ha"]["inputs"] == ["x"]


def test_first_hours_count_the_scans_the_passes_and_the_time_that_the_sensors_saw():
    hour = 3600.0
    # At longitude -60 the solar time is 4 hours before UTC. Four detections:
    # GOES at 20:00 and 20:05 local (one scan from two sources) and at 21:00, VIIRS at 14:00.
    detections = {
        "observed": np.array([24 * hour, 24 * hour + 300, 25 * hour, 18 * hour]),
        "lon": np.array([-60.0, -60.0, -60.0, -60.0]),
        "family": np.array(["abi", "abi", "abi", "viirs"]),
        "platform": np.array(["GOES16", "GOES16", "GOES16", "NOAA20"]),
    }
    found = risk_inputs.first_hours_inputs(detections, np.arange(4))
    # The first detection is at 14:00 at the place: the angle of 14 of 24 hours.
    assert round(found["hour_sin"], 4) == round(float(np.sin(2 * np.pi * 14 / 24)), 4)
    assert round(found["abi_scans_log"], 4) == round(float(np.log(1 + 2)), 4)
    assert round(found["abi_night_scans_log"], 4) == round(float(np.log(1 + 2)), 4)
    assert round(found["polar_passes_log"], 4) == round(float(np.log(1 + 1)), 4)
    assert round(found["span_h_log"], 4) == round(float(np.log(1 + 7)), 4)
    only_goes = risk_inputs.first_hours_inputs(detections, np.array([0]))
    assert (only_goes["polar_passes_log"], only_goes["span_h_log"]) == (0.0, 0.0)
    assert set(found) == set(risk_inputs.FIRST_HOURS)


def set_row(name: str, auc: float, large: int, expected: float | None) -> dict:
    ratio = None if expected is None else large / expected
    row = {"inputs": name, "moment_h": "0", "limit_ha": 100.0, "auc": auc, "large": large}
    level = {"large": large, "expected_large": expected, "observed_to_expected": ratio}
    return row | {f"recalibrated_{name}": value for name, value in level.items()}


def test_rule_asks_for_a_larger_auc_in_most_years_and_a_level_that_is_not_worse(monkeypatch):
    monkeypatch.setattr("chispa.config.RISK_RULE_MIN_YEARS", 2)
    monkeypatch.setattr("chispa.config.RISK_RULE_LEVEL_MARGIN", 0.05)
    monkeypatch.setattr("chispa.config.RISK_RULE_MIN_MODELS", 1)
    monkeypatch.setattr("chispa.config.RISK_LEVEL_YEAR", (0.5, 2.0))
    # Three years. The first year is not a scored year: it has no level.
    # "with more" has a larger AUC in each year, and its level is 20 of 34: farther from 1
    # than 20 of 32, by less than the margin. "with less" has a larger AUC in one year only.
    by_year = {
        2001: [set_row("inputs now", 0.70, 5, None), set_row("with more", 0.72, 5, None)],
        2002: [set_row("inputs now", 0.70, 10, 16.0), set_row("with more", 0.71, 10, 17.0)],
        2003: [set_row("inputs now", 0.80, 10, 16.0), set_row("with more", 0.82, 10, 17.0)],
    }
    by_year[2001].append(set_row("with less", 0.75, 5, None))
    by_year[2002].append(set_row("with less", 0.60, 10, 16.0))
    by_year[2003].append(set_row("with less", 0.70, 10, 16.0))
    table = {row["inputs"]: row for row in rule_table(by_year, removes={"with less"})}
    more = table["with more"]
    assert (more["tested"], more["years_larger"], more["years"]) == ("with more", 3, 3)
    assert (more["level"], more["level_other"]) == (round(20 / 34, 4), 0.625)
    assert (more["passes"], more["models_passed"], more["stays"]) == (True, 1, True)
    # A set that removes inputs: the inputs of now are tested, and they pass in 2 of 3 years.
    less = table["with less"]
    assert (less["tested"], less["years_larger"], less["passes"]) == ("inputs now", 2, True)
    # With a margin of zero the larger set does not pass: 20 of 34 is farther from 1.
    monkeypatch.setattr("chispa.config.RISK_RULE_LEVEL_MARGIN", 0.0)
    assert rule_table(by_year, removes=set())[0]["passes"] is False


def test_weather_inputs_use_the_days_before_and_the_days_from_the_day_of_the_moment(monkeypatch):
    monkeypatch.setattr("chispa.config.RISK_RAIN_DAYS", (2, 4))
    monkeypatch.setattr("chispa.config.RISK_RAIN_DAY_MM", 1.0)
    monkeypatch.setattr("chispa.config.RISK_WEATHER_DAYS", 2)
    monkeypatch.setattr("chispa.config.RISK_WEATHER_LATE_DAYS", 0)
    monkeypatch.setattr(risk_inputs, "RAIN", ("rain_2d_log", "rain_4d_log"))
    # Six days. The day of the moment is day 4. The last day with rain before it is day 1.
    series = {
        "rain_mm": np.array([0.0, 5.0, 0.2, 0.0, 9.0, 1.0]),
        "wind_kmh": np.array([10.0, 12.0, 20.0, 30.0, 8.0, 40.0]),
        "vpd_kpa": np.array([1.0, 1.0, 2.0, 4.0, 0.5, 3.0]),
    }
    found = risk_inputs.weather_inputs(series, 4)
    assert round(found["rain_2d_log"], 4) == round(float(np.log(1 + 0.2)), 4)
    assert round(found["rain_4d_log"], 4) == round(float(np.log(1 + 5.2)), 4)
    # Day 1 had rain, and the days 2 and 3 had less than 1 mm: 2 days with no rain.
    assert round(found["no_rain_days_log"], 4) == round(float(np.log(1 + 2)), 4)
    assert (found["wind_before_kmh"], found["vpd_before_kpa"]) == (25.0, 3.0)
    assert (found["wind_after_kmh"], found["vpd_after_kpa"]) == (40.0, 3.0)
    assert round(found["rain_after_log"], 4) == round(float(np.log(1 + 10.0)), 4)
    # With no delay of the product, the late inputs are equal to the inputs before.
    assert found["rain_4d_log_late"] == found["rain_4d_log"]
    # A series that starts too late for the day of the moment is an error, not a wrong value.
    with pytest.raises(ValueError, match="starts too late"):
        risk_inputs.weather_inputs(series, 3)
    # With no day of rain in the days before, the value is the longest time that we examine.
    series["rain_mm"] = np.zeros(6)
    dry = risk_inputs.weather_inputs(series, 4)["no_rain_days_log"]
    assert round(dry, 4) == round(float(np.log(1 + 4)), 4)


def test_late_weather_inputs_stop_some_days_before_the_usual_end(monkeypatch):
    monkeypatch.setattr("chispa.config.RISK_RAIN_DAYS", (2,))
    monkeypatch.setattr("chispa.config.RISK_WEATHER_DAYS", 1)
    monkeypatch.setattr("chispa.config.RISK_WEATHER_LATE_DAYS", 3)
    monkeypatch.setattr(risk_inputs, "RAIN", ("rain_2d_log",))
    # Ten days. The day of the moment is day 8: the late inputs are those of day 5.
    series = {
        "rain_mm": np.array([0.0, 0.0, 0.0, 4.0, 2.0, 0.0, 0.0, 1.0, 0.0, 0.0]),
        "wind_kmh": np.arange(10.0),
        "vpd_kpa": np.ones(10),
    }
    found = risk_inputs.weather_inputs(series, 8)
    assert round(found["rain_2d_log"], 4) == round(float(np.log(1 + 1.0)), 4)
    assert round(found["rain_2d_log_late"], 4) == round(float(np.log(1 + 6.0)), 4)
    assert (found["wind_before_kmh"], found["wind_before_kmh_late"]) == (7.0, 4.0)


def test_ground_that_burned_before_gives_the_years_the_times_and_the_share_near(monkeypatch):
    monkeypatch.setattr("chispa.config.RISK_BURNED_CELL_SHARE", 0.5)
    monkeypatch.setattr("chispa.config.RISK_BURNED_NEAR_CELLS", 3)
    monkeypatch.setattr("chispa.config.RISK_BURNED_NEAR_YEARS", (1, 2))
    monkeypatch.setattr(risk_inputs, "BURNED_NEAR", ("burned_near_1y", "burned_near_2y"))
    # Three years of a grid of 3 rows and 3 columns, the oldest year first.
    oldest = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]])
    middle = np.array([[0.6, 0.4, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]])
    newest = np.array([[0.0, 0.0, 0.0], [0.0, 0.9, 0.0], [0.0, 0.0, 0.0]])
    found = risk_inputs.burned_layers([oldest, middle, newest])
    # The corner cell burned in the two oldest years: its last burn is 2 years before.
    # The centre cell burned the year before. A cell with no burn gets 3 + 1 years.
    years = found["burned_years_log"]
    assert round(float(years[0, 0]), 4) == round(float(np.log(2)), 4)
    assert (float(years[1, 1]), round(float(years[2, 2]), 4)) == (0.0, round(float(np.log(4)), 4))
    # A share of 0.4 is less than half of the cell: no burn.
    assert round(float(years[0, 1]), 4) == round(float(np.log(4)), 4)
    assert found["burned_times"].tolist() == [[2.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 0.0]]
    # The square of the centre cell is the 9 cells: 0.9 of 9 burned in the year before.
    assert round(float(found["burned_near_1y"][1, 1]), 4) == 0.1
    # For 2 years a cell counts with its largest share: 0.6 + 0.4 + 0.9 of 9 cells.
    assert round(float(found["burned_near_2y"][1, 1]), 4) == round(1.9 / 9, 4)
    # A cell at the edge has a part of its square out of the grid: that part counts as no burn.
    assert round(float(found["burned_near_1y"][0, 0]), 4) == 0.1
    assert set(found) == {"burned_years_log", "burned_times", "burned_near_1y", "burned_near_2y"}


def test_river_inputs_use_the_days_before_the_day_of_the_moment(monkeypatch):
    monkeypatch.setattr("chispa.config.RISK_RIVER_CHANGE_DAYS", 2)
    first = datetime(2020, 1, 1, tzinfo=UTC).date()
    levels = {first.replace(day=day): level for day, level in ((2, 1.0), (3, 1.2), (4, 1.5))}
    levels[first.replace(day=5)] = 9.0
    # The day of the moment is 5 January: the level is that of 4 January, and not of 5 January.
    found = risk_inputs.river_inputs(levels, first.replace(day=5))
    assert found == {"river_m": 1.5, "river_change_m": 0.5}
    # A day with no level is an error, not a wrong value.
    with pytest.raises(ValueError, match="chispa fetch river --year 2020"):
        risk_inputs.river_inputs(levels, first.replace(day=4))


def test_level_of_the_alerts_with_only_goes_rows_of_inpe_is_apart(monkeypatch):
    monkeypatch.setattr("chispa.config.RISK_LIMITS_HA", (100.0,))
    # The model gives each alert the probability 0.5: x is 0, and the start is 0.
    rows = [alert(0.0, 500.0), alert(0.0, 0.0), alert(0.0, 0.0), alert(0.0, 0.0)]
    rows += [alert(0.0, 0.0, only_inpe_goes=True), alert(0.0, 0.0, only_inpe_goes=True)]
    table = source_table({"0": rows, "24": rows[:4]}, {"0h_100ha": MODEL, "24h_100ha": MODEL})
    found = {(row["moment_h"], row["group"]): row for row in table}
    only = found[("0", "only GOES rows of INPE")]
    # Two alerts with 0.5 each expect one large alert, and none came.
    assert (only["alerts"], only["large"], only["expected_large"]) == (2, 0, 1.0)
    assert only["observed_to_expected"] == 0.0
    other = found[("0", "each other alert")]
    assert (other["alerts"], other["large"], other["observed_to_expected"]) == (4, 1, 0.5)
    # A group with no alert has no level.
    assert found[("24", "only GOES rows of INPE")]["observed_to_expected"] is None


def test_tables_for_a_new_fire_use_only_the_alerts_with_a_new_fire(monkeypatch):
    monkeypatch.setattr("chispa.config.RISK_LIMITS_HA", (100.0,))
    monkeypatch.setattr("chispa.evaluation.risk.names_of", lambda moment: ("x",))
    monkeypatch.setattr(risk_run, "INPUT_SETS", {"inputs now": ((), ())})
    # Ten new fires of 500 hectares with x = 1, and ten new fires of 50 hectares with x = 0.
    fire = [alert(float(n % 2), 500.0 if n % 2 else 50.0) for n in range(20)]
    # These alerts are not in the question: no mapped fire, and a known fire. They say the opposite.
    out = [alert(1.0, 0.0)] * 30 + [alert(0.0, 500.0, known=True)] * 30
    parts = {year: {"rows": {"0": fire + out, "24": fire + out}} for year in (2001, 2002)}
    tables = risk_run.fire_tables(parts)
    assert set(tables[2001]) == {"risk_fire"}
    assert set(tables[2002]) == {"risk_fire", "risk_fire_calibration"}
    first = tables[2002]["risk_fire"][0]
    assert (first["inputs"], first["alerts"], first["large"], first["auc"]) == (
        "inputs now",
        20,
        10,
        1.0,
    )
    # The model of 2001 expects the ten large alerts of 2002, and it is better than the base rate.
    all_alerts = tables[2002]["risk_fire_calibration"][0]
    assert (all_alerts["group"], all_alerts["alerts"], all_alerts["large"]) == ("all", 20, 10)
    assert 0.9 < all_alerts["observed_to_expected"] < 1.1
    assert all_alerts["brier_skill"] > 0.5
