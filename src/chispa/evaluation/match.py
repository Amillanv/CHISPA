"""The match rule: which detection belongs to which fire.

A detection has a position, a footprint and a time. A fire has pixels and burn days.
All measures of the evaluation use the matches that this module makes.
"""

import numpy as np

from chispa import config
from chispa.grid import Grid

Fields = dict[str, np.ndarray]  # one array for each field of the detections or of the fires
Pairs = tuple[np.ndarray, np.ndarray]  # detection index and fire number of each match


def near_in_time(fires: Fields, found: np.ndarray, month: int, day: int) -> np.ndarray:
    """Return True for each fire number in `found` that burned near the time of a detection.

    A fire with burn days: the day of the detection is in the burn days, plus the day margin.
    A fire with no burn day: the detection is in the map month or in the months before it.
    """
    first, last = fires["first_day"][found], fires["last_day"][found]
    by_day = (day >= first - config.EVAL_DAY_MARGIN) & (day <= last + config.EVAL_DAY_MARGIN)
    months_before = fires["month"][found] - month
    by_month = (months_before >= 0) & (months_before <= config.EVAL_MONTHS_BEFORE)
    return np.where(first > 0, by_day, by_month)


def match(detections: Fields, numbers: np.ndarray, grid: Grid, fires: Fields) -> Pairs:
    """Return (detection index, fire number) for each detection that matches a fire.

    A detection matches a fire if a pixel of the fire is in the square of the footprint
    plus the margin, and the fire burned near the time of the detection, in the year of the map.
    """
    reach_m = detections["footprint_m"] + config.EVAL_MARGIN_M
    d_rows = np.ceil(reach_m / (grid.pixel_deg * 110_574)).astype(int)
    d_cols = np.ceil(
        reach_m / (grid.pixel_deg * 111_320 * np.cos(np.deg2rad(detections["lat"])))
    ).astype(int)
    rows, cols = grid.rows_cols(detections["lat"], detections["lon"])
    months, days = detections["month"], detections["day"]
    # A detection of a different year is not on a fire of this map: its month and its day are
    # those of its own year. A detection of 31 December can be available in the next year.
    seconds = detections["observed"].astype(np.int64).astype("datetime64[s]")
    in_year = seconds.astype("datetime64[Y]").astype(int) + 1970 == fires["year"]
    pair_detection, pair_fire = [], []
    for i in np.flatnonzero(in_year):
        window = numbers[
            max(rows[i] - d_rows[i], 0) : rows[i] + d_rows[i] + 1,
            max(cols[i] - d_cols[i], 0) : cols[i] + d_cols[i] + 1,
        ]
        if not window.any():
            continue
        found = np.unique(window)
        found = found[found > 0]
        found = found[near_in_time(fires, found, months[i], days[i])]
        pair_detection += [i] * len(found)
        pair_fire += found.tolist()
    return np.array(pair_detection, dtype=int), np.array(pair_fire, dtype=int)


def isolated(pairs: Pairs, fires: Fields) -> np.ndarray:
    """Return True for each counted fire that shares no detection with a different counted fire.

    Only for such a fire we know that each of its detections belongs to it,
    for a sensor with a small footprint and for a sensor with a large footprint.
    """
    counted = fires["counted"][pairs[1]]
    pair_detection, pair_fire = pairs[0][counted], pairs[1][counted]
    fires_of_detection = np.bincount(pair_detection)
    shared = np.zeros(len(fires["counted"]), dtype=bool)
    shared[pair_fire[fires_of_detection[pair_detection] > 1]] = True
    return fires["counted"] & ~shared


def first_times(pairs: Pairs, chosen: np.ndarray, times: np.ndarray, count: int) -> np.ndarray:
    """Return, for each fire number, the first time of a chosen detection that matches it.

    A fire with no chosen detection gets infinity. `count` is the number of fires.
    """
    pair_detection, pair_fire = pairs
    keep = chosen[pair_detection]
    first = np.full(count + 1, np.inf)
    np.minimum.at(first, pair_fire[keep], times[pair_detection[keep]])
    return first
