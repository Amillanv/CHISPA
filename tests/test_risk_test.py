"""Tests of the rows of the test year of the growth risk."""

from datetime import UTC, datetime

from chispa.evaluation import risk_recalibration, risk_test
from chispa.evaluation.risk_test import known_until, replay_table

DAY = 86_400.0


def test_outcome_is_known_the_delay_after_the_moment_of_an_alert(monkeypatch):
    monkeypatch.setattr("chispa.config.RISK_RECALIBRATION_DELAY_DAYS", 60)
    # The map has the months to October: it ends at the start of 1 November.
    # 60 days before that is the start of 2 September.
    assert known_until(2026, 10) == datetime(2026, 9, 2, tzinfo=UTC)
    # A map to December ends at the start of the next year.
    assert known_until(2025, 12) == datetime(2025, 11, 2, tzinfo=UTC)


def test_replay_gives_an_alert_the_factor_of_the_map_that_it_had(monkeypatch):
    monkeypatch.setattr("chispa.config.RISK_RECALIBRATION_DELAY_DAYS", 1)
    monkeypatch.setattr("chispa.config.RISK_RECALIBRATION_WINDOW_DAYS", 1000)
    monkeypatch.setattr("chispa.config.RISK_RECALIBRATION_PRIOR", 1.0)
    monkeypatch.setattr("chispa.config.RISK_CLASS_LIMITS_HA", (100.0,))
    monkeypatch.setattr("chispa.config.RISK_TEST_MIN_LARGE", 2)
    monkeypatch.setattr("chispa.config.RISK_LEVEL_YEAR", (0.5, 2.0))
    monkeypatch.setattr(risk_recalibration, "MOMENTS", ("0",))
    monkeypatch.setattr(risk_test, "MOMENTS", ("0",))

    def alert(number: int, day: float, size_ha: float) -> dict:
        row = {"alert": number, "inputs": {"x": 0.0}, "size_ha": size_ha, "known": False}
        row |= {"near_earlier": number == 8}  # The alert 8 is near an earlier alert.
        return row | {"at": day * DAY, "only_inpe_goes": False, "matched": size_ha > 0}

    # The model gives each alert the value 0.5. The year before has 10 alerts on the days 0 to 9.
    # With the map of the end, the alerts 0 and 1 became large.
    model = {"inputs": ["x"], "mean": [0.0], "spread": [1.0], "start": 0.0, "weights": [1.0]}
    models = {year: {"0h_100ha": model | {"base_rate": 0.5}} for year in (2002, 2003)}
    before = [alert(number, float(number), 500.0 if number < 2 else 0.0) for number in range(10)]
    # The test year: 2 alerts on day 400 and 2 on day 500. One of each day became large.
    test = [alert(20 + n, 400.0 + 100 * (n // 2), 500.0 * (n % 2)) for n in range(4)]

    def state(large: tuple, known: tuple = ()) -> dict:
        found = {n: {"size_ha": 500.0 * (n in large), "seen_ha": 0.0} for n in range(10)}
        return {2002: {"0": {n: row | {"known": n in known} for n, row in found.items()}}}

    # To day 450 the map had only the fire of alert 0, and alert 9 was on a known fire.
    # From day 450 the map has the two fires, as the map of the end.
    states = [(0.0, state(large=(0,), known=(9,))), (450 * DAY, state(large=(0, 1)))]
    parts = {2002: {"rows": {"0": before}}, 2003: {"rows": {"0": test}, "states": states}}
    found = replay_table(parts, models, 2003)[0]
    # Day 400: 9 alerts, 1 large for 4.5 expected: a factor of 2 divided by 5.5, a value of 4/15.
    # Day 500: 10 alerts, 2 large for 5 expected: a factor of 0.5, a value of 1 in 3.
    assert (found["alerts"], found["large"]) == (4, 2)
    assert found["expected_large"] == round(2 * 4 / 15 + 2 / 3, 1)
    assert found["factor_median"] == round((2 / 5.5 + 0.5) / 2, 4)
    assert found["observed_to_expected"] == round(2 / (2 * 4 / 15 + 2 / 3), 4)
    # The level is 1.6667: in the range of one year.
    assert found["level_in_range"] is True
    # With the mark of the detections, the alert 8 is left out at each time, and the alert 9 is
    # not: the mark of the map is not read. Day 400: 9 alerts again. Day 500: 9 alerts, 2 large
    # for 4.5 expected: a factor of 3 divided by 5.5, a value of 3 divided by 8.5.
    marked = replay_table(parts, models, 2003, mark=True)[0]
    assert (marked["alerts"], marked["large"]) == (4, 2)
    assert marked["observed_to_expected"] == round(2 / (2 * 4 / 15 + 2 * 3 / 8.5), 4)
