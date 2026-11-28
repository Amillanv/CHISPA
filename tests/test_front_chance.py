"""Tests of the chance of a front for an alert that only GOES started, with cases for paper."""

from datetime import UTC, date, datetime, timedelta

import numpy as np
import pytest

from chispa.evaluation import front_chance

LAT, LON = -19.0, -57.0
ALERT = datetime(2023, 9, 1, 12, 0, tzinfo=UTC).timestamp()  # The first detection of an alert.
HOUR = 3600.0


@pytest.fixture(autouse=True)
def fixed_values(monkeypatch):
    monkeypatch.setattr("chispa.config.LOOK_GAP", timedelta(hours=3))
    monkeypatch.setattr("chispa.config.FRONT_LINK_M", 1500.0)
    monkeypatch.setattr("chispa.config.PASS_GAP", timedelta(minutes=30))
    monkeypatch.setattr("chispa.config.SEVERITY_EVAL_HOURS", 24.0)
    monkeypatch.setattr("chispa.config.FRONT_ALERT_DELAYS_H", (0.5, 24))
    monkeypatch.setattr("chispa.config.FRONT_TEST_END", datetime(2026, 11, 21, tzinfo=UTC))
    monkeypatch.setattr("chispa.config.FORECAST_BANDS", (0.05, 0.1, 0.2, 0.35, 0.5, 0.7))
    monkeypatch.setattr("chispa.config.CONFIDENCE_PENALTY", 0.001)


def test_the_weather_of_a_year_in_progress_ends_with_its_last_complete_month(tmp_path):
    for name in ("2025/01.npz", "2026/10.npz", "2026/11.npz.part"):
        (tmp_path / "weather" / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "weather" / name).touch()
    # A complete year has the weather to 10 January of the next year, as the growth risk.
    assert front_chance.weather_last(tmp_path, 2024) == date(2025, 1, 10)
    # November 2026 is a month in progress: its file is not complete.
    assert front_chance.weather_last(tmp_path, 2026) == date(2026, 10, 31)
    with pytest.raises(RuntimeError, match="chispa fetch weather --year 2022"):
        front_chance.weather_last(tmp_path, 2022)


def test_only_an_alert_with_goes_detections_and_a_second_moment_in_the_year_is_a_row(monkeypatch):
    # Five detections: three of GOES, then one of VIIRS, then one of GOES.
    detections = {"family": np.array(["abi", "abi", "abi", "viirs", "abi"])}
    at = datetime(2023, 12, 31, 12, 0, tzinfo=UTC).timestamp()
    rows = [
        {"alert": 1, "at": ALERT + 1800, "positions": np.array([0, 1])},
        {"alert": 2, "at": ALERT + 1800, "positions": np.array([2, 3])},  # GOES and VIIRS.
        {"alert": 3, "at": at, "positions": np.array([4])},  # 24 hours later is the next year.
    ]
    monkeypatch.setattr(front_chance, "biome_detections", lambda *arguments: detections)
    monkeypatch.setattr(front_chance, "year_rows", lambda *arguments: ({"0": rows}, None))
    monkeypatch.setattr(front_chance, "weather_last", lambda raw_dir, year: date(2024, 1, 10))
    monkeypatch.setattr(front_chance, "add_model_inputs", lambda *arguments: None)
    assert [row["alert"] for row in front_chance.goes_alerts(2023, None, None)] == [1]
    # The weather ends on 31 August: the alert of 1 September has no weather for its day.
    monkeypatch.setattr(front_chance, "weather_last", lambda raw_dir, year: date(2023, 8, 31))
    rows[0]["positions"] = np.array([0, 1])
    assert front_chance.goes_alerts(2023, None, None) == []


def test_an_alert_has_a_front_if_a_viirs_pixel_was_available_at_the_second_moment(monkeypatch):
    # (issued id, observed, available, lat, lon). The pixel of the alert 1 was available 13 hours
    # after the first detection. That of the alert 2 was available 30 hours after it.
    pixels = np.array(
        [
            (1, ALERT + 10 * HOUR, ALERT + 13 * HOUR, LAT, LON),
            (2, ALERT + 27 * HOUR, ALERT + 30 * HOUR, LAT, LON),
        ]
    )
    monkeypatch.setattr(front_chance.front_alerts, "load", lambda store, year: (pixels, []))
    monkeypatch.setattr(front_chance.sqlite3, "connect", lambda path: None)
    # The moment of a row is one pass gap after the first detection of its alert.
    rows = [{"alert": number, "at": ALERT + 1800} for number in (1, 2, 3)]
    found = front_chance.with_fronts(rows, None, 2023)
    assert [row["front"] for row in found] == [True, False, False]


def row_of(detections_log: float, front: bool) -> dict:
    """An alert with one input that is not 0: the number of its detections."""
    inputs = dict.fromkeys((*front_chance.NAMES, "detections_log"), 0.0)
    return {"inputs": inputs | {"detections_log": detections_log}, "front": front}


BASELINE = {"inputs": ["detections_log"], "mean": [0.0], "spread": [1.0]}
BASELINE |= {"start": 0.0, "weights": [1.0]}


def test_a_model_with_no_sign_gives_each_alert_the_share_of_the_training_rows():
    # Each alert has the same inputs. 1 of the 4 training alerts had a front.
    training = [row_of(0.0, True)] + [row_of(0.0, False)] * 3
    rows = [row_of(0.0, True), row_of(0.0, False)]
    tables = front_chance.year_tables(rows, training, BASELINE)
    (row,) = tables["front_chance"]
    assert (row["alerts"], row["with_front"], row["share"]) == (2, 1, 0.5)
    # Each chance is 0.25: the sum is 0.5, no pair is in sequence, and the skill is 0.
    assert (row["training_share"], row["expected"]) == (0.25, 0.5)
    assert (row["auc_model"], row["brier_skill"]) == (0.5, 0.0)


def test_a_model_with_a_sign_puts_the_alerts_with_a_front_first():
    # In the training rows, the alerts with more detections had a front.
    training = [row_of(0.0, False), row_of(0.0, False), row_of(1.0, True), row_of(1.0, True)]
    rows = [row_of(0.0, False), row_of(1.0, True), row_of(1.0, True), row_of(0.0, False)]
    tables = front_chance.year_tables(rows, training, BASELINE)
    (row,) = tables["front_chance"]
    assert (row["auc_model"], row["auc_confidence"], row["auc_detections"]) == (1.0, 1.0, 1.0)
    # Each alert has the same hour: the baseline of the hour puts no pair in sequence.
    assert row["auc_hour"] == 0.5
    # The two groups are equal in size: the chances are p and 1 - p, and their sum is 2.
    assert row["expected"] == 2.0 and row["brier_skill"] > 0
    assert tables["front_chance_weights"][0]["input"] == "detections_log"
    assert sum(band["rows"] for band in tables["front_chance_bands"]) == 4
    assert sum(band["came"] for band in tables["front_chance_bands"]) == 2


def test_a_year_gets_the_model_of_the_other_development_years(monkeypatch, tmp_path):
    monkeypatch.setattr("chispa.config.FRONT_YEARS", (2019, 2020))
    monkeypatch.setattr("chispa.config.FRONT_TEST_YEARS", (2021,))
    monkeypatch.setattr(front_chance, "goes_alerts", lambda year, *arguments: [f"alert {year}"])
    monkeypatch.setattr(front_chance, "with_fronts", lambda rows, *arguments: rows)
    monkeypatch.setattr(front_chance.confidence, "load", lambda path: {"0": "confidence"})
    monkeypatch.setattr(
        front_chance, "year_tables", lambda rows, training, baseline: (rows, training, baseline)
    )
    tables = front_chance.chance_tables(tmp_path, tmp_path, test_run=False)
    assert tables == {
        2019: (["alert 2019"], ["alert 2020"], "confidence"),
        2020: (["alert 2020"], ["alert 2019"], "confidence"),
    }
    tables = front_chance.chance_tables(tmp_path, tmp_path, test_run=True)
    assert tables[2021] == (["alert 2021"], ["alert 2019", "alert 2020"], "confidence")
    # A year with no row stops the run: it cannot have a table.
    monkeypatch.setattr(front_chance, "goes_alerts", lambda year, *arguments: [])
    with pytest.raises(RuntimeError, match="no alert of 2019 that only GOES started"):
        front_chance.chance_tables(tmp_path, tmp_path, test_run=False)
