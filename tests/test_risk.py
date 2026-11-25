"""Tests of the growth risk: the new fires, the size of an alert, the measures and the years."""

import json

import numpy as np

from chispa.evaluation import risk
from chispa.evaluation.risk import (
    average_precision,
    calibration_table,
    fit_models,
    group_table,
    key,
    measures,
    result_table,
    seen_first,
    sized_rows,
    weight_table,
)


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


def test_alert_has_the_area_of_its_largest_new_fire_and_a_known_fire_is_left_out():
    area_ha = np.array([0.0, 0.0, 0.0, 0.0, 0.0, 50.0, 2000.0, 300.0])
    first = {5: 1, 6: 1, 7: 2}
    rows = [
        {"alert": 1, "own_fires": frozenset({5})},  # It saw the fires 5 and 6 first.
        {"alert": 2, "own_fires": frozenset({7, 5})},  # On fire 5, which alert 1 saw first.
        {"alert": 3, "own_fires": frozenset()},  # No mapped fire.
        {"alert": 4, "own_fires": frozenset({6})},  # On fire 6: a known fire.
    ]
    kept = sized_rows(rows, first, area_ha)
    assert [(row["alert"], row["size_ha"]) for row in kept] == [(1, 2000.0), (3, 0.0)]


def test_measures_count_the_large_alerts_and_their_sequence(monkeypatch):
    monkeypatch.setattr("chispa.config.RISK_LARGEST_HA", 10000.0)
    # 10 alerts. The value is in the sequence of the sizes. Two alerts became large.
    size = np.array([0, 0, 0, 0, 0, 0, 50, 150, 1500, 20000], dtype=float)
    found = measures(np.arange(10, dtype=float), size, 1000.0)
    assert (found["alerts"], found["large"], found["base_rate"], found["new_fires"]) == (
        10,
        2,
        0.2,
        4,
    )
    assert (found["auc"], found["auc_new_fires"], found["average_precision"]) == (1.0, 1.0, 1.0)
    assert (found["top_tenth"], found["top_tenth_large"]) == (1, 1)
    assert (found["precision_top_tenth"], found["recall_top_tenth"]) == (1.0, 0.5)
    assert (found["largest_fires"], found["top_tenth_largest_fires"]) == (1, 1)
    # A value that finds the alerts with a fire, and puts their sizes in the wrong sequence:
    # 2 large alerts against 8 others give 16 pairs, and 12 of them are in the correct sequence.
    wrong = np.array([0, 0, 0, 0, 0, 0, 9, 8, 7, 6], dtype=float)
    found = measures(wrong, size, 1000.0)
    assert (found["auc"], found["auc_new_fires"]) == (0.75, 0.0)
    # The two large alerts are at places 3 and 4: precision 1 of 3 and 2 of 4.
    assert found["average_precision"] == round((1 / 3 + 2 / 4) / 2, 4)


def test_average_precision_of_equal_values_is_the_base_rate():
    large = np.array([True, False, True, False])
    assert average_precision(np.array([3.0, 2.0, 1.0, 0.0]), large) == round((1 + 2 / 3) / 2, 4)
    assert average_precision(np.ones(4), large) == 0.5
    assert average_precision(np.ones(4), np.zeros(4, dtype=bool)) is None


def alert(x: float, size_ha: float, advance_m: float | None = None) -> dict:
    row = {"inputs": {"x": x, "detections_log": -x}, "size_ha": size_ha, "advance_m": advance_m}
    return row | {"matched": size_ha > 0, "alert": int(x)}


def test_table_compares_the_growth_risk_with_each_baseline(monkeypatch):
    monkeypatch.setattr("chispa.config.RISK_LIMITS_HA", (100.0,))
    monkeypatch.setattr("chispa.config.RISK_LARGEST_HA", 10000.0)
    model = {"inputs": ["x"], "mean": [0.0], "spread": [1.0], "start": 0.0, "weights": [1.0]}
    against = model | {"weights": [-1.0]}
    # The largest fire is the only alert with a measured advance.
    rows = [alert(0, 0.0), alert(1, 0.0), alert(2, 150.0), alert(3, 20000.0, 900.0)]
    kept = {"0": rows, "24": rows}
    models = {key("0", 100.0): model, key("24", 100.0): model}
    table = result_table(kept, models, {"0": against, "24": against})
    found = {(row["moment_h"], row["value"]): row["auc"] for row in table}
    assert found[("0", "growth_risk")] == 1.0
    assert found[("0", "confidence")] == 0.0
    assert found[("0", "detections")] == 0.0
    # The alert with the advance is before the two alerts that are not large: 2 pairs of 4.
    # For the other large alert, each value is equal: a half for its 2 pairs.
    assert found[("24", "persistence")] == 0.75
    assert ("0", "persistence") not in found


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
    table = group_table({"0": kept + [{}], "24": kept}, {"0": kept, "24": kept}, fires)
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
    model = {"inputs": ["x"], "mean": [0.0], "spread": [1.0], "start": 0.0, "weights": [1.0]}
    folder = tmp_path / "2023" / "confidence"
    folder.mkdir(parents=True)
    (folder / "model.json").write_text(json.dumps({"0": model, "24": model}))
    # In 2001 and 2002 a large x is a large fire. In 2003 a small x is a large fire.
    usual = [alert(float(n % 2), 500.0 * (n % 2)) for n in range(20)]
    other = [alert(float(n % 2), 500.0 * (1 - n % 2)) for n in range(20)]
    saved = {year: {"kept": {"0": usual, "24": usual}, "alerts": []} for year in (2001, 2002)}
    saved[2003] = {"kept": {"0": other, "24": other}, "alerts": []}
    monkeypatch.setattr(risk, "saved_rows", lambda year, store, raw: saved[year])
    by_year = {
        year: risk.risk_tables(year, tmp_path / "store", tmp_path)["risk"][0]["auc"]
        for year in (2002, 2003)
    }
    # The model of 2002 learned from 2001 and 2003: the two years disagree, and 2001 has as
    # many rows as 2003. The model of 2003 learned only the usual years: it is wrong for 2003.
    assert by_year[2003] == 0.0
    assert by_year[2002] in (0.5, 1.0, 0.0)


def test_calibration_gives_the_brier_skill_and_the_observed_against_the_expected(monkeypatch):
    monkeypatch.setattr("chispa.config.RISK_LIMITS_HA", (100.0, 1000.0))
    monkeypatch.setattr("chispa.evaluation.risk.TENTHS", 2)
    # A model with no weight gives each alert its start value: 0 is a probability of 0.5.
    model = {"inputs": ["x"], "mean": [0.0], "spread": [1.0], "start": 0.0, "weights": [0.0]}
    model |= {"base_rate": 0.5}
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
