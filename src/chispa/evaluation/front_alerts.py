"""The first alerts that have a front, at some delays after the alert.

The growth forecast is for a front: the minimum number of linked VIIRS pixels of one look. A first
alert frequently has less: one GOES pixel, or one VIIRS pixel. This module counts, for the first
alerts of a year in the biome, how many have a front at each delay. A first alert is an event as
we issued it: its first detection, at its position of that moment, before a later merge.
It uses only the detections that the event of the alert had at each moment.
`docs/method.md` section 11.26 gives the rule.
"""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from chispa import config, fronts
from chispa.evaluation.fronts import SOURCE
from chispa.evaluation.report import share
from chispa.grid import pantanal_grid
from chispa.issued import Replay
from chispa.sources import border

# One row for each issued id of a year: the time when its first detection was available, the
# sensor families of the detections of that time, and their mean position. An event that a later
# merge absorbed had its own first alert, and an event can start above the lowest level: thus
# the table of alerts, which has the events of the end of the year, does not give this.
ALERTS = """
WITH first AS (
  SELECT m.issued_id AS id, MIN(d.available_at) AS at
  FROM memberships m JOIN detections d ON d.id = m.detection_id
  WHERE m.issued_id >= ? AND m.issued_id < ? GROUP BY m.issued_id
)
SELECT first.id, CAST(strftime('%s', first.at) AS INTEGER),
       GROUP_CONCAT(DISTINCT d.sensor_family), AVG(d.lat), AVG(d.lon)
FROM first JOIN memberships m ON m.issued_id = first.id
JOIN detections d ON d.id = m.detection_id AND d.available_at = first.at
GROUP BY first.id
"""
PIXELS = """
SELECT m.issued_id, CAST(strftime('%s', d.observed_at) AS INTEGER),
       CAST(strftime('%s', d.available_at) AS INTEGER), d.lat, d.lon
FROM detections d JOIN memberships m ON m.detection_id = d.id
WHERE d.sensor_family = ? AND d.source = ? AND d.observed_at >= ? AND d.observed_at < ?
ORDER BY m.issued_id
"""
MERGES = "SELECT CAST(strftime('%s', at) AS INTEGER), absorbed_id, into_id FROM merges"
FIRST_FAMILY = {"goes": "abi", "viirs": "viirs"}  # The alerts that only this family started.


def has_front(observed: np.ndarray, points: np.ndarray) -> bool:
    """Return True if the newest look of these pixels has a front of the minimum size."""
    if len(observed) < config.FRONT_MIN_PIXELS:
        return False
    look = fronts.looks(observed)
    newest = points[look == look.max()]
    if len(newest) < config.FRONT_MIN_PIXELS:
        return False
    return int(np.bincount(fronts.fronts(newest)).max()) >= config.FRONT_MIN_PIXELS


def front_flags(alerts: list[tuple], pixels: np.ndarray, merges: list[tuple]) -> np.ndarray:
    """Return, for each alert and each delay, True if the event of the alert had a front then.

    An alert is (issued id, time in seconds). `pixels` has (issued id, observed, available, lat,
    lon) for each VIIRS pixel, in the sequence of the issued ids. At a moment, an event has the
    pixels of its issued ids of that moment (`issued.py`) that were available.
    """
    delays = config.FRONT_ALERT_DELAYS_H
    replay, flags = Replay(merges), np.zeros((len(alerts), len(delays)), dtype=bool)
    points = fronts.metres(pixels[:, 3], pixels[:, 4])
    moments = [
        (alert[1] + delay * 3600, number, column)
        for number, alert in enumerate(alerts)
        for column, delay in enumerate(delays)
    ]
    for moment, number, column in sorted(moments):
        replay.advance(moment)
        ids = replay.ids(alerts[number][0])
        spans = [np.searchsorted(pixels[:, 0], [one, one + 1]) for one in ids]
        own = np.concatenate([np.arange(first, last) for first, last in spans])
        own = own[pixels[own, 2] <= moment]
        flags[number, column] = has_front(pixels[own, 1], points[own])
    return flags


def in_biome_alerts(alerts: list[tuple], raw_dir: Path) -> list[tuple]:
    """Return the alerts with their position of the first moment in the biome border."""
    grid = pantanal_grid()
    inside = border.rasterize(border.read_rings(raw_dir / "border" / "pantanal.geojson"), grid)
    lat, lon = np.array([row[3] for row in alerts]), np.array([row[4] for row in alerts])
    keep = inside[grid.rows_cols(lat, lon)]
    return [row for row, one in zip(alerts, keep, strict=True) if one]


def table(year: int, store_path: Path, raw_dir: Path) -> list[dict]:
    """Return the table `front_alerts` of one year: one row for each delay after the alert."""
    store = sqlite3.connect(store_path)
    span = (f"{year}-01-01", f"{year + 1}-01-01")
    ids = (year * config.EVENT_IDS_OF_A_YEAR, (year + 1) * config.EVENT_IDS_OF_A_YEAR)
    alerts = in_biome_alerts(store.execute(ALERTS, ids).fetchall(), raw_dir)
    # An alert needs its longest delay in the year, and before the end of a year in progress.
    end = datetime(year + 1, 1, 1, tzinfo=UTC).timestamp()
    end = min(end - max(config.FRONT_ALERT_DELAYS_H) * 3600, config.FRONT_TEST_END.timestamp())
    alerts = [row for row in alerts if row[1] < end]
    found = store.execute(PIXELS, (fronts.SENSOR_FAMILY, SOURCE, *span)).fetchall()
    pixels = np.array(found, dtype=float).reshape(-1, 5)
    flags = front_flags(alerts, pixels, [tuple(row) for row in store.execute(MERGES)])
    family = np.array([row[2] for row in alerts])
    rows = []
    for column, delay in enumerate(config.FRONT_ALERT_DELAYS_H):
        with_front = int(flags[:, column].sum())
        row = {"delay_h": delay, "alerts": len(alerts), "with_front": with_front}
        row["share"] = share(with_front, len(alerts))
        for name, value in FIRST_FAMILY.items():
            row[f"{name}_first"] = int((family == value).sum())
            row[f"{name}_first_with_front"] = int(flags[family == value, column].sum())
        rows.append(row)
    return rows
