"""The activity of a region in a window: the events and the detections of each time step.

The dashboard shows how the activity changed before the as-of time, and when each sensor
family gave detections. The unit of the event count is the event as it was at the as-of time
(`issued.py`): the same event that `alerts_near` gives. An event counts in a step if one of its
detections became available in that step, with the level after its newest detection of the step.
"""

import sqlite3
from datetime import datetime, timedelta

from chispa import record
from chispa.fusion import LEVELS
from chispa.store import to_text

# A step number counts back from the as-of time: step 0 ends at the as-of time.
BACK = "(? - CAST(strftime('%s', d.available_at) AS INTEGER)) / ?"
WINDOW = """
WHERE d.available_at > ? AND d.available_at <= ?
  AND d.lat BETWEEN ? AND ? AND d.lon BETWEEN ? AND ?
"""
# One row for each alert and step: the newest detection of the alert in the step, with its level.
ALERTS = f"""
SELECT back, issued_id, available_at, level FROM (
  SELECT back, issued_id, available_at, level,
         ROW_NUMBER() OVER (PARTITION BY back, issued_id ORDER BY available_at DESC, id DESC) AS n
  FROM (
    SELECT {BACK} AS back, m.issued_id, d.available_at, d.id, m.level
    FROM detections d JOIN memberships m ON m.detection_id = d.id {WINDOW}
  )
) WHERE n = 1
"""
FAMILIES = f"SELECT {BACK}, d.sensor_family, COUNT(*) FROM detections d {WINDOW} GROUP BY 1, 2"
NEWEST = f"SELECT d.sensor_family, MAX(d.observed_at) FROM detections d {WINDOW} GROUP BY 1"


def steps(
    store: sqlite3.Connection, box: tuple, as_of: datetime, hours: float, step_hours: float
) -> dict:
    """Return the events and the detections in the box for each step of the window.

    `box` is west, south, east, north in degrees. The window is the `hours` before `as_of`,
    in steps of `step_hours`, the oldest step first. A step includes its end and not its start.
    """
    west, south, east, north = box
    step_s = round(step_hours * 3600)
    count = round(hours / step_hours)
    window = (to_text(as_of - timedelta(hours=hours)), to_text(as_of), south, north, west, east)
    back = (int(as_of.timestamp()), step_s)
    events = _events(store, as_of, store.execute(ALERTS, (*back, *window)), count)
    detections: list[dict] = [{} for _ in range(count)]
    for number, family, found in store.execute(FAMILIES, (*back, *window)):
        detections[number][family] = found
    rows = []
    for number in range(count - 1, -1, -1):
        end = as_of - timedelta(seconds=number * step_s)
        rows.append(
            {
                "start": to_text(end - timedelta(seconds=step_s)),
                "end": to_text(end),
                "events": events[number],
                "detections": detections[number],
            }
        )
    return {
        "as_of": to_text(as_of),
        "hours": hours,
        "step_hours": step_hours,
        "steps": rows,
        "newest_observed_at": dict(store.execute(NEWEST, window).fetchall()),
    }


def _events(store: sqlite3.Connection, as_of: datetime, alerts, count: int) -> list[dict]:
    """Return the number of events of each level for each step, from the rows of ALERTS.

    Two alerts that are one event at the as-of time count one time in a step. The event has
    the level after the newer of their two newest detections in that step.
    """
    replay = record.replay_at(store, as_of)
    newest: dict[tuple[int, int], tuple[str, int]] = {}
    for number, issued_id, available_at, level in alerts:
        key, value = (number, replay.root(issued_id)), (available_at, LEVELS.index(level))
        newest[key] = max(newest.get(key, value), value)
    events = [dict.fromkeys(LEVELS, 0) for _ in range(count)]
    for (number, _), (_, level) in newest.items():
        events[number][LEVELS[level]] += 1
    return events
