"""Measured growth: how far an event moved between two VIIRS passes, and in which direction.

A detection says that a pixel had heat. Many detections of one fire, pass after pass,
show where the fire went. The measure is a distance, not an area: a VIIRS pixel is as large
as a small fire, thus the area of the pixels is not the burned area (`docs/method.md` 11.12).
"""

import numpy as np
from scipy.spatial import cKDTree

from chispa import config

SENSOR_FAMILY = "viirs"  # A GOES pixel is too large to show a movement.


def passes(platform: np.ndarray, observed: np.ndarray) -> np.ndarray:
    """Return the pass number of each detection of one event, in time sequence from 0.

    Detections of one platform are one pass if their times are not farther apart than the pass gap.
    """
    order = np.lexsort((observed, platform))  # By platform, then by time.
    names, times = platform[order], observed[order]
    gap_s = config.PASS_GAP.total_seconds()
    first = np.concatenate([[True], (names[1:] != names[:-1]) | (np.diff(times) > gap_s)])
    start = times[first]  # The first time of each pass.
    rank = np.argsort(np.argsort(start, kind="stable"), kind="stable")
    numbers = np.empty(len(order), dtype=int)
    numbers[order] = rank[np.cumsum(first) - 1]
    return numbers


def steps(lat: np.ndarray, lon: np.ndarray, pass_number: np.ndarray, observed: np.ndarray) -> list:
    """Return one row for each pass after the first pass of an event.

    A row has the time of the pass, the hours from the pass before, the number of pixels,
    the advance in metres, the number of new pixels, the direction in degrees from north,
    and the speed in metres for each hour.
    The advance is a high percentile of the distance from each pixel to the nearest older pixel.
    A step with no pixel farther than the floor in `config.py` has no direction and no speed.
    A step with a short time from the pass before has no speed: there the error of the
    positions, divided by the time, gives a high value.
    """
    north_m = lat * 110_574
    east_m = lon * 111_320 * np.cos(np.deg2rad(lat.mean()))
    points = np.column_stack([north_m, east_m])
    times = [observed[pass_number == number].min() for number in range(pass_number.max() + 1)]
    rows = []
    for number in range(1, len(times)):
        older, now = points[pass_number < number], points[pass_number == number]
        distance, nearest = cKDTree(older).query(now)
        new = distance > config.GROWTH_FLOOR_M
        line = (now[new] - older[nearest[new]]).mean(axis=0) if new.any() else None
        hours = float(times[number] - times[number - 1]) / 3600
        advance_m = float(np.percentile(distance, config.GROWTH_ADVANCE_PERCENT))
        has_speed = line is not None and hours >= config.GROWTH_SPEED_MIN_H
        rows.append(
            {
                "at": float(times[number]),
                "hours": hours,
                "pixels": len(now),
                "advance_m": advance_m,
                "new_pixels": int(new.sum()),
                "direction_deg": None if line is None else _bearing(line),
                "speed_m_h": advance_m / hours if has_speed else None,
            }
        )
    return rows


def _bearing(line: np.ndarray) -> float:
    """Return the direction of a line (metres north, metres east) in degrees from north."""
    return float(np.degrees(np.arctan2(line[1], line[0])) % 360)
