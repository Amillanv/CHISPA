"""Inputs of the growth risk for the state of the season.

The share of the alerts that become large changes with the year, and the inputs of the confidence
do not have the state of the season. This module gives each alert the dryness of its place,
from the fields that INPE adds to the rows of its archive files.
`docs/method.md` section 11.22 gives the rules.
"""

from pathlib import Path

import numpy as np

from chispa.evaluation.match import Fields
from chispa.sources import inpe

DRYNESS = ("dry_days_log", "rain_mm_log", "fire_risk", "no_dryness", "no_fire_risk")
# The sets of inputs that the table `risk_inputs` compares: a name, and the inputs that the set
# adds to the inputs of the confidence.
INPUT_SETS = {"inputs now": (), "with dryness": DRYNESS}


def dryness_of(detections: Fields, raw_dir: Path, year: int) -> np.ndarray:
    """Return the dryness of each detection of a year: three values in a row, NaN for no value.

    Only an INPE detection has a row in an archive file. The time and the position of a
    detection find its row: the store has them as the file has them.
    """
    found = {}
    for path in inpe.year_files(raw_dir, year):
        for time, lat, lon, *values in inpe.dryness_rows(path):
            found[(int(time.timestamp()), round(lat, 5), round(lon, 5))] = values
    table = np.full((len(detections["lat"]), 3), np.nan)
    for position in np.flatnonzero(detections["source"] == "inpe"):
        lat, lon = float(detections["lat"][position]), float(detections["lon"][position])
        values = found.get((int(detections["observed"][position]), round(lat, 5), round(lon, 5)))
        if values is not None:
            table[position] = [np.nan if value is None else value for value in values]
    return table


def dryness_inputs(dryness: np.ndarray, positions: np.ndarray) -> dict[str, float]:
    """Return the dryness inputs of one alert, from the detections that it has at the moment.

    Each value is the median over its detections with a value. An alert with no such detection
    gets 0 for the value and a mark, as an alert with no fire power does (`confidence.inputs`).
    """
    days, rain, risk = (column[~np.isnan(column)] for column in dryness[positions].T)
    return {
        "dry_days_log": float(np.log1p(np.median(days))) if len(days) else 0.0,
        "rain_mm_log": float(np.log1p(np.median(rain))) if len(rain) else 0.0,
        "fire_risk": float(np.median(risk)) if len(risk) else 0.0,
        "no_dryness": float(len(days) == 0),
        "no_fire_risk": float(len(risk) == 0),
    }
