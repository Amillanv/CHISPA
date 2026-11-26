"""Tests of the rows of the test year of the growth risk."""

from datetime import UTC, datetime

from chispa.evaluation.risk_test import known_until


def test_outcome_is_known_the_delay_after_the_moment_of_an_alert(monkeypatch):
    monkeypatch.setattr("chispa.config.RISK_RECALIBRATION_DELAY_DAYS", 60)
    # The map has the months to October: it ends at the start of 1 November.
    # 60 days before that is the start of 2 September.
    assert known_until(2026, 10) == datetime(2026, 9, 2, tzinfo=UTC)
    # A map to December ends at the start of the next year.
    assert known_until(2025, 12) == datetime(2025, 11, 2, tzinfo=UTC)
