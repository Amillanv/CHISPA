"""When could CHISPA use a live row? The time of its first read, or an estimate for a late read.

The poller records when it first read each row. After a stop of the poller that time is late:
it is the time of our stop, not the time of the source. A long pass after a stop has the same
effect on the files that it reads last. GOES and INPE give the publication time of each file.
Thus a row that the poller read late gets the time that a poller with no stop gives: the
publication time plus the normal wait to the next pass. The logs keep the measured time, and
the detection has a mark (`available_estimated`). The owner agreed to this rule on 2026-11-24.
"""

from datetime import datetime

from chispa import config


def live_available(first_seen_at: datetime, published_at: datetime) -> tuple[datetime, bool]:
    """Return the time when CHISPA could use a live row, and True if that time is an estimate."""
    if first_seen_at - published_at > config.LIVE_POLL_LATE:
        return published_at + config.LIVE_NORMAL_WAIT, True
    return first_seen_at, False
