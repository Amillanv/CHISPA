"""Tests of the growth forecast, with cases small enough for paper."""

import numpy as np
import pytest

from chispa.evaluation import forecast
from chispa.evaluation import fronts as steps


@pytest.fixture(autouse=True)
def fixed_values(monkeypatch):
    monkeypatch.setattr("chispa.config.FRONT_SECTORS", 8)
    monkeypatch.setattr("chispa.config.FRONT_LARGE_PIXELS", 10)
    monkeypatch.setattr("chispa.config.FRONT_DIRECTION_PIXELS", 3)
    monkeypatch.setattr("chispa.config.ADVANCE_SAME_DEG", 45.0)
    monkeypatch.setattr("chispa.config.FORECAST_LEAVES", (4,))
    monkeypatch.setattr("chispa.config.FORECAST_MAX_TREES", 20)
    monkeypatch.setattr("chispa.config.FORECAST_MIN_LEAF", 5)


def one_sector(number: int, count: int = 1) -> np.ndarray:
    """A row for each front with 1 in one sector and 0 in the others."""
    row = np.zeros((count, 8))
    row[:, number] = 1.0
    return row


def rows_of_three_fronts() -> dict:
    """Front 0 has 12 new pixels to the east. Front 1 was not visible. Front 2 has no weather."""
    answers = {"answer_12": np.array([0, steps.HIDDEN, 2]), "new_12": np.array([12, 0, 0])}
    answers["sectors_12"] = np.concatenate([12 * one_sector(2), np.zeros((2, 8))])
    inputs = {"log_pixels": np.array([1.0, 2.0, 3.0]), "past_vpd": np.array([4.0, 4.0, np.nan])}
    inputs |= {"log_came": np.array([0.7, 0.0, 0.0]), "log_fresh": np.zeros(3)}
    inputs["log_frp_mean"] = np.full(3, 2.0)
    inputs |= {"came_share_s": np.zeros((3, 8)), "past_wind_toward_s": np.ones((3, 8))}
    return {"answers": answers, "inputs": inputs | {"came_direction_deg": np.full(3, np.nan)}}


def test_a_front_that_was_not_visible_or_has_no_weather_is_not_a_row():
    found = forecast.case(rows_of_three_fronts(), "new_ground", 12)
    assert found["fronts"].tolist() == [True, False, False]
    assert (found["y"].tolist(), found["persistence"].tolist()) == ([1.0], [0.7])
    assert "came_direction_deg" not in found["names"] and "came_share_s" not in found["names"]


def test_a_front_with_no_fire_power_is_not_a_row():
    rows = rows_of_three_fronts()
    rows["inputs"]["log_frp_mean"] = np.array([np.nan, 2.0, 2.0])
    assert forecast.case(rows, "new_ground", 12)["fronts"].tolist() == [False, False, False]


def test_large_growth_needs_the_minimum_number_of_new_pixels(monkeypatch):
    assert forecast.case(rows_of_three_fronts(), "large_growth", 12)["y"].tolist() == [1.0]
    monkeypatch.setattr("chispa.config.FRONT_LARGE_PIXELS", 13)
    assert forecast.case(rows_of_three_fronts(), "large_growth", 12)["y"].tolist() == [0.0]


def test_the_sector_question_has_one_row_for_each_sector_of_a_front():
    found = forecast.case(rows_of_three_fronts(), "sector", 12)
    assert found["x"].shape == (8, len(found["names"]))
    assert found["y"].tolist() == [0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    assert found["x"][:, found["names"].index("log_pixels")].tolist() == [1.0] * 8
    assert found["wind"].tolist() == [1.0] * 8


def test_the_scores_of_a_question():
    held = {"y": np.array([1.0, 0.0, 1.0, 0.0]), "persistence": np.array([0.0, 0.0, 2.0, 1.0])}
    chances = {"trees": np.array([0.9, 0.2, 0.6, 0.4])}
    found = forecast.scores(held, chances, 0.5)
    assert (found["rows"], found["positive"]) == (4, 2)
    # Persistence: of the four pairs of a 1 and a 0, two have the correct sequence and one is equal.
    assert (found["auc_trees"], found["auc_persistence"]) == (1.0, 0.625)
    # Trees: (0.01 + 0.04 + 0.16 + 0.16) / 4. The share: 0.25 for each row.
    assert (found["brier_trees"], found["brier_share"]) == (0.0925, 0.25)
    assert found["brier_skill"] == 0.63


def test_the_direction_of_a_model_is_the_mean_of_its_sectors():
    # Two fronts with 5 new pixels. Front 0 went to 100 degrees, and front 1 to 180 degrees.
    rows = {"answers": {"new_12": np.array([5, 5]), "direction_deg_12": np.array([100.0, 180.0])}}
    rows["inputs"] = {"came_direction_deg": np.array([300.0, np.nan])}
    rows["inputs"]["wind_direction_deg"] = np.array([80.0, 170.0])
    held = {"fronts": np.array([True, True])}
    # The model says east for front 0 (90 degrees) and north for front 1 (0 degrees).
    chances = {"trees": np.concatenate([one_sector(2), one_sector(0)]).ravel()}
    found = forecast.direction_row(rows, 12, held, chances)
    assert (found["fronts"], found["trees_in_45"], found["wind_in_45"]) == (2, 1, 2)
    assert (found["fronts_with_persistence"], found["persistence_in_45"]) == (1, 0)
    assert found["trees_in_45_of_them"] == 1


def test_the_trees_learn_a_simple_rule_and_give_the_same_answer_each_time():
    # 300 rows of three years. The label is 1 if the first input is more than 0.
    values = np.random.default_rng(1).normal(size=(300, 3))
    label, years = (values[:, 0] > 0).astype(float), np.repeat([2019, 2020, 2021], 100)
    first = forecast.fit_trees(values, label, years).predict_proba(values)[:, 1]
    second = forecast.fit_trees(values, label, years).predict_proba(values)[:, 1]
    assert ((first > 0.5) == (label > 0)).mean() > 0.95
    assert first.tolist() == second.tolist()
