"""Tests of the recalibration of the growth risk, with cases that a person can calculate."""

import numpy as np
import pytest

from chispa.evaluation import risk_recalibration
from chispa.evaluation.risk_recalibration import (
    class_rows,
    percentage_table,
    recalibration_tables,
)
from chispa.risk import factors, recalibrate

DAY = 86_400.0


def settings(monkeypatch, delay: int, window: int, prior: float) -> None:
    monkeypatch.setattr("chispa.config.RISK_RECALIBRATION_DELAY_DAYS", delay)
    monkeypatch.setattr("chispa.config.RISK_RECALIBRATION_WINDOW_DAYS", window)
    monkeypatch.setattr("chispa.config.RISK_RECALIBRATION_PRIOR", prior)


def test_factor_uses_only_the_outcomes_that_are_known_and_in_the_window(monkeypatch):
    settings(monkeypatch, delay=2, window=10, prior=1.0)
    # Three older alerts, on the days 0, 5 and 9. The first two became large.
    past = {
        "time": np.array([0.0, 5.0, 9.0]) * DAY,
        "value": np.array([0.5, 0.5, 0.25]),
        "large": np.array([1.0, 1.0, 0.0]),
    }
    found = factors(np.array([1.0, 8.0, 12.0]) * DAY, past)
    # Day 1: no alert is 2 days old. The factor is the prior divided by the prior.
    assert found[0] == 1.0
    # Day 8: the alerts of the days 0 and 5 are known. 2 came for 1.0 expected: 3 divided by 2.
    assert found[1] == 1.5
    # Day 12: day 0 is out of the window of 10 days. 1 came for 0.75 expected: 2 divided by 1.75.
    assert round(float(found[2]), 4) == round(2 / 1.75, 4)


def test_recalibration_multiplies_the_odds():
    # Odds of 1 times 3 are odds of 3: a value of 0.75. A factor of 1 changes nothing.
    found = recalibrate(np.array([0.5, 0.2]), np.array([3.0, 1.0]))
    assert [round(float(value), 4) for value in found] == [0.75, 0.2]


def test_classes_come_from_the_two_values_and_a_wrong_sequence_gets_the_smaller(monkeypatch):
    monkeypatch.setattr("chispa.config.RISK_CLASS_LIMITS_HA", (100.0, 1000.0))
    # The second alert has a larger value for 1000 hectares than for 100: a wrong sequence.
    for_100, for_1000 = np.array([0.5, 0.2]), np.array([0.1, 0.3])
    table = class_rows([for_100, for_1000], np.array([500.0, 0.0]))
    found = {row["class"]: row for row in table}
    assert list(found) == [
        "less than 100 hectares",
        "100 to 1000 hectares",
        "1000 hectares or more",
    ]
    # Less than 100: 0.5 + 0.8. Between: 0.4 + 0. 1000 or more: 0.1 + 0.2. The sum is 2 alerts.
    expected = [row["expected_alerts"] for row in table]
    assert expected == [1.3, 0.4, 0.3]
    assert [row["alerts"] for row in table] == [1, 1, 0]
    assert found["100 to 1000 hectares"]["observed_to_expected"] == 2.5
    assert {row["wrong_sequence_alerts"] for row in table} == {1}


def alert(day: float, size_ha: float, only_inpe_goes: bool = False) -> dict:
    row = {"inputs": {"x": 0.0}, "size_ha": size_ha, "known": False, "at": day * DAY}
    return row | {"only_inpe_goes": only_inpe_goes, "matched": size_ha > 0}


def test_scored_year_gets_the_factor_of_the_year_before(monkeypatch):
    settings(monkeypatch, delay=1, window=1000, prior=1.0)
    monkeypatch.setattr("chispa.config.RISK_CLASS_LIMITS_HA", (100.0,))
    monkeypatch.setattr("chispa.config.RISK_MIN_TRAINING_YEARS", 2)
    monkeypatch.setattr("chispa.config.RISK_LEVEL_YEAR", (0.5, 2.0))
    monkeypatch.setattr("chispa.config.RISK_LEVEL_ALL", (0.8, 1.25))
    monkeypatch.setattr(risk_recalibration, "MOMENTS", ("0",))
    # The model gives each alert the value 0.5. In 2002, 2 of 10 alerts became large.
    model = {"inputs": ["x"], "mean": [0.0], "spread": [1.0], "start": 0.0, "weights": [1.0]}
    model |= {"base_rate": 0.5}
    second = [alert(day, 500.0 if day < 2 else 0.0) for day in range(10)]
    # In 2003, 2 of 6 alerts became large, all on day 400. One more alert has only GOES rows
    # of INPE: it gets a rank only. An alert on a known fire is not in the question.
    third = [alert(400.0, 500.0 if number < 2 else 0.0) for number in range(6)]
    third += [alert(400.0, 500.0, only_inpe_goes=True), alert(400.0, 500.0) | {"known": True}]
    parts = {2001: {"rows": {"0": []}}, 2002: {"rows": {"0": second}}, 2003: {"rows": {"0": third}}}
    models = {year: {"0h_100ha": model} for year in (2002, 2003)}
    tables = recalibration_tables(parts, models)
    # 2002 has one training year: it is not scored.
    assert set(tables) == {2003}
    first = tables[2003]["risk_recalibrated"][0]
    assert (first["group"], first["alerts"], first["large"], first["rank_only_alerts"]) == (
        "all",
        6,
        2,
        1,
    )
    # The outcomes of 2002 are known: 2 came for 5 expected. The factor is 3 divided by 6.
    assert (first["factor_smallest"], first["factor_largest"]) == (0.5, 0.5)
    # Each alert of the year has the same value before and after: the AUC is that of chance.
    assert (first["auc_before"], first["auc"]) == (0.5, 0.5)
    # Before: 6 alerts with 0.5 expect 3. After: odds of 0.5, a value of 1 in 3, expect 2.
    assert (first["expected_large_before"], first["expected_large"]) == (3.0, 2.0)
    assert (first["observed_to_expected_before"], first["observed_to_expected"]) == (0.6667, 1.0)
    # The Brier score of the value 1 in 3 is 0.2222, and that of the base rate 0.5 is 0.25.
    assert (first["brier_skill_before"], first["brier_skill"]) == (0.0, 0.1111)
    rule = {row["values"]: row for row in tables[2003]["risk_percentage"]}
    assert rule["recalibrated"]["percentage"] is True
    # Before the recalibration the value is the base rate: it is not better than the base rate.
    assert rule["before"]["better_than_base_rate_each_year"] is False
    assert rule["before"]["percentage"] is False
    assert [row["class"] for row in tables[2003]["risk_classes"]] == [
        "less than 100 hectares",
        "100 hectares or more",
    ]


def test_year_with_no_alert_for_a_percentage_says_why(monkeypatch):
    settings(monkeypatch, delay=1, window=1000, prior=1.0)
    monkeypatch.setattr("chispa.config.RISK_CLASS_LIMITS_HA", (100.0,))
    monkeypatch.setattr("chispa.config.RISK_MIN_TRAINING_YEARS", 2)
    monkeypatch.setattr(risk_recalibration, "MOMENTS", ("0",))
    model = {"inputs": ["x"], "mean": [0.0], "spread": [1.0], "start": 0.0, "weights": [1.0]}
    model |= {"base_rate": 0.5}
    second = [alert(day, 500.0 if day < 2 else 0.0) for day in range(10)]
    # Each alert of 2003 has only GOES rows of INPE, or is on a known fire.
    third = [alert(400.0, 500.0, only_inpe_goes=True), alert(400.0, 500.0) | {"known": True}]
    parts = {2001: {"rows": {"0": []}}, 2002: {"rows": {"0": second}}, 2003: {"rows": {"0": third}}}
    models = {year: {"0h_100ha": model} for year in (2002, 2003)}
    with pytest.raises(RuntimeError, match="No alert of 2003 can get a percentage"):
        recalibration_tables(parts, models)


def test_percentage_needs_each_of_the_three_conditions(monkeypatch):
    monkeypatch.setattr("chispa.config.RISK_LEVEL_YEAR", (0.5, 2.0))
    monkeypatch.setattr("chispa.config.RISK_LEVEL_ALL", (0.8, 1.25))

    def row(skill: float, large: int, expected: float) -> dict:
        found = {"moment_h": "0", "limit_ha": 100.0, "group": "all", "large": large}
        found |= {"brier_skill": skill, "expected_large": expected}
        found |= {"observed_to_expected": round(large / expected, 4)}
        return found | {f"{name}_before": value for name, value in list(found.items())[4:]}

    # Two years. Together: 30 large alerts for 30 expected. The second year has 20 for 8: 2.5.
    by_year = {2001: [row(0.1, 10, 22.0)], 2002: [row(0.2, 20, 8.0)]}
    found = percentage_table(by_year)[0]
    assert (found["level_all_years"], found["level_largest"]) == (1.0, 2.5)
    assert found["better_than_base_rate_each_year"] and found["level_all_years_in_range"]
    assert not found["level_each_year_in_range"] and not found["percentage"]
    # A year with a skill of 0 is not better than the base rate.
    by_year = {2001: [row(0.0, 10, 10.0)], 2002: [row(0.2, 20, 20.0)]}
    assert percentage_table(by_year)[0]["percentage"] is False


def answer_row(large: int, skill: float | None, level: float | None) -> dict:
    row = {"moment_h": "0", "limit_ha": 100.0, "group": "all", "alerts": 500, "large": large}
    row |= {"expected_large": 30.0, "factor_median": 1.0}
    return row | {"auc": 0.8, "brier_skill": skill, "observed_to_expected": level}


def test_answer_of_the_test_year_needs_enough_large_alerts(monkeypatch):
    monkeypatch.setattr("chispa.config.RISK_TEST_MIN_LARGE", 30)
    monkeypatch.setattr("chispa.config.RISK_LEVEL_YEAR", (0.5, 2.0))
    rows = [answer_row(40, 0.05, 1.2), answer_row(40, 0.05, 2.5), answer_row(40, -0.01, 1.0)]
    # A tenth is not a model: it gives no answer row.
    rows += [answer_row(29, 0.05, 1.2), answer_row(40, 0.05, 1.2) | {"group": "3"}]
    found = risk_recalibration.answer_table(rows)
    assert [row["percentage_holds"] for row in found] == [True, False, False, None]
    # The second model has a level out of the range, and the third is not better than the base rate.
    assert (found[1]["level_in_range"], found[2]["better_than_base_rate"]) == (False, False)
    # 29 large alerts are too few: the model has no answer.
    assert found[3]["enough_large_alerts"] is False


def test_test_year_gets_its_own_tables_and_no_table_of_the_conditions(monkeypatch):
    settings(monkeypatch, delay=1, window=1000, prior=1.0)
    monkeypatch.setattr("chispa.config.RISK_CLASS_LIMITS_HA", (100.0,))
    monkeypatch.setattr("chispa.config.RISK_MIN_TRAINING_YEARS", 2)
    monkeypatch.setattr("chispa.config.RISK_TEST_MIN_LARGE", 2)
    monkeypatch.setattr(risk_recalibration, "MOMENTS", ("0",))
    model = {"inputs": ["x"], "mean": [0.0], "spread": [1.0], "start": 0.0, "weights": [1.0]}
    model |= {"base_rate": 0.5}
    # 2002 has a map: 2 of 10 alerts became large. 2003 is the test year: 2 of 6 on day 400.
    second = [alert(day, 500.0 if day < 2 else 0.0) for day in range(10)]
    third = [alert(400.0, 500.0 if number < 2 else 0.0) for number in range(6)]
    parts = {2001: {"rows": {"0": []}}, 2002: {"rows": {"0": second}}, 2003: {"rows": {"0": third}}}
    models = {year: {"0h_100ha": model} for year in (2002, 2003)}
    tables = recalibration_tables(parts, models, test_year=2003)
    assert set(tables) == {2003}
    assert set(tables[2003]) == {"risk_recalibrated", "risk_classes", "risk_test"}
    answer = tables[2003]["risk_test"][0]
    # As for the scored year: the factor of 2002 gives a level of 1 and a skill of 0.1111.
    assert (answer["large"], answer["observed_to_expected"], answer["brier_skill"]) == (
        2,
        1.0,
        0.1111,
    )
    assert answer["percentage_holds"] is True
