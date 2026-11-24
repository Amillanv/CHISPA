"""Tests of the time when CHISPA could use a live row, for paper."""

from datetime import UTC, datetime, timedelta

from chispa.arrival import live_available

PUBLISHED = datetime(2026, 11, 22, 12, 10, tzinfo=UTC)


def test_row_of_normal_operation_keeps_the_time_of_the_first_view(monkeypatch):
    monkeypatch.setattr("chispa.config.LIVE_POLL_LATE", timedelta(minutes=15))
    seen = PUBLISHED + timedelta(minutes=15)
    assert live_available(seen, PUBLISHED) == (seen, False)


def test_row_that_a_pass_saw_after_a_stop_gets_the_publication_time_plus_the_wait(monkeypatch):
    monkeypatch.setattr("chispa.config.LIVE_POLL_LATE", timedelta(minutes=15))
    monkeypatch.setattr("chispa.config.LIVE_NORMAL_WAIT", timedelta(minutes=3))
    # The poller was back two days later. A poller with no stop has the row 3 minutes
    # after its publication.
    seen = PUBLISHED + timedelta(days=2)
    assert live_available(seen, PUBLISHED) == (PUBLISHED + timedelta(minutes=3), True)
