"""The detections of each alert at a moment after its first detection.

A check of a value at a moment must use the alert as a brigade had it at that moment.
An alert is an issued id: the event that started with one detection. At a moment, its event
holds the alerts that merged with it up to that moment, and not the alerts that merged later.
An alert that merged into an older event before the moment is not an alert at that moment:
a brigade sees it as a part of the older event. Thus it gives no row.
"""

import sqlite3

import numpy as np

from chispa.evaluation.match import Fields
from chispa.issued import Replay

MERGES = """
SELECT CAST(strftime('%s', at) AS INTEGER), absorbed_id, into_id FROM merges
WHERE into_id >= ? AND into_id < ?
"""


def load_merges(store: sqlite3.Connection, year: int) -> list[tuple[float, int, int]]:
    """Return (time in seconds, the id that stops, the id that continues) for each merge."""
    first_id = year * 10_000_000
    return [tuple(row) for row in store.execute(MERGES, (first_id, first_id + 10_000_000))]


def at_moments(detections: Fields, merges: list, limits: dict[str, float]):
    """Give (moment, alert, its own detections, the detections of its event at the moment).

    `limits` gives the seconds of each moment after the first detection of an alert.
    The two last values are positions in the detection arrays. The first of them has only
    the detections that joined this alert. The second has all detections of the event of the
    alert as it was at the moment. An alert that is a part of an older event at the moment
    is not given.
    """
    order = np.argsort(detections["issued"], kind="stable")
    ids, starts = np.unique(detections["issued"][order], return_index=True)
    ends = [*starts[1:], len(order)]
    own = {int(i): order[s:e] for i, s, e in zip(ids, starts, ends, strict=True)}
    available = detections["available"]
    requests = sorted(
        (float(available[positions].min()) + limit, moment, alert)
        for alert, positions in own.items()
        for moment, limit in limits.items()
    )
    replay = Replay(merges)
    for time, moment, alert in requests:
        replay.advance(time)
        if replay.root(alert) != alert:
            continue
        members = np.concatenate([own[i] for i in replay.ids(alert) if i in own])
        yield moment, alert, own[alert], members[available[members] <= time]
