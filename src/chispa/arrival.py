"""When could CHISPA use a live row? The time of the first view, or an estimate after a stop.

The poller records when it first saw each row. After a stop of the poller that time is late:
it is the time of our stop, not the time of the source. GOES and INPE give the publication
time of each file. Thus a row that the poller saw late gets the time that a poller with no
stop gives: the publication time plus the normal wait to the next pass.
"""

from datetime import datetime

from chispa import config


def live_available(first_seen_at: datetime, published_at: datetime) -> tuple[datetime, bool]:
    """Return the time when CHISPA could use a live row, and True if that time is an estimate."""
    if first_seen_at - published_at > config.LIVE_POLL_LATE:
        return published_at + config.LIVE_NORMAL_WAIT, True
    return first_seen_at, False
