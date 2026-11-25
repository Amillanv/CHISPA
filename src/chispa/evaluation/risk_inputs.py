"""Inputs of the growth risk for the state of the season.

The share of the alerts that become large changes with the year, and the inputs of the confidence
do not have the state of the season. This module gives each alert the dryness of its place,
from the fields that INPE adds to the rows of its archive files.
`docs/method.md` section 11.22 gives the rules.
"""

from pathlib import Path

import numpy as np

from chispa import config, growth
from chispa.evaluation.match import Fields
from chispa.sources import inpe

DRYNESS = ("dry_days_log", "rain_mm_log", "fire_risk", "no_dryness", "no_fire_risk")
HOURS = ("hour_sin", "hour_cos", "abi_scans_log", "abi_night_scans_log", "polar_passes_log")
FIRST_HOURS = (*HOURS, "span_h_log")
CALENDAR = ("season_sin", "season_cos")
RAIN = tuple(f"rain_{days}d_log" for days in config.RISK_RAIN_DAYS)
WEATHER_BEFORE = (*RAIN, "no_rain_days_log", "wind_before_kmh", "vpd_before_kpa")
WEATHER_AFTER = ("wind_after_kmh", "vpd_after_kpa", "rain_after_log")
WEATHER_LATE = tuple(f"{name}_late" for name in WEATHER_BEFORE)
EXPOSURE = ("people_log", "protected_km_log", "indigenous_km_log")
# The sets of inputs that the table `risk_inputs` compares. A set has a name, the inputs that
# it adds to the inputs of now, and the inputs of now that it removes.
# The inputs that the models have and the confidence does not have: the groups that passed the
# rule on 2026-11-25. The weather is the late weather: an alert can have it at its time.
# Each set below is a change of the inputs of now. For a set with a name that starts with
# "without", the inputs of now are tested against the set. For each other set, the set is tested.
ADOPTED = FIRST_HOURS + WEATHER_LATE
POWER = ("power_log", "no_power")
# The inputs of the confidence that the models do not have: they did not pass the rule on
# 2026-11-25. The weather in the models replaced the calendar. The fire power and its mark made
# the level worse: the years before August 2022 have a fire power for few GOES rows.
REMOVED = CALENDAR + POWER
INPUT_SETS = {
    "inputs now": ((), ()),
    "without first hours": ((), FIRST_HOURS),
    "without weather": ((), WEATHER_LATE),
    "weather before for weather late": (WEATHER_BEFORE, WEATHER_LATE),
    "with weather after": (WEATHER_AFTER, ()),
    "with calendar": (CALENDAR, ()),
    "with fire power": (POWER, ()),
    "with dryness": (DRYNESS, ()),
    "without people and land": ((), EXPOSURE),
}


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


def first_hours_inputs(detections: Fields, positions: np.ndarray) -> dict[str, float]:
    """Return how long, and at which hours, the sensors saw an alert up to the moment.

    The hour is the solar hour at the place. A GOES scan with a row from two sources counts one
    time: the scans are counted by their start time. Night is from 18:00 to 06:00, as the
    input `night` of the confidence.
    """
    observed = detections["observed"][positions].astype(float)
    hour = (observed / 3600 + detections["lon"][positions] / 15) % 24
    abi = detections["family"][positions] == "abi"
    night = (hour < 6) | (hour >= 18)
    scan_s = config.GOES_SCAN.total_seconds()
    platform, passes = detections["platform"][positions][~abi], 0
    if len(platform):
        passes = int(growth.passes(platform, observed[~abi]).max()) + 1
    angle = 2 * np.pi * hour[observed.argmin()] / 24
    return {
        "hour_sin": float(np.sin(angle)),
        "hour_cos": float(np.cos(angle)),
        "abi_scans_log": float(np.log1p(len(np.unique(observed[abi] // scan_s)))),
        "abi_night_scans_log": float(np.log1p(len(np.unique(observed[abi & night] // scan_s)))),
        "polar_passes_log": float(np.log1p(passes)),
        "span_h_log": float(np.log1p((observed.max() - observed.min()) / 3600)),
    }


def weather_inputs(series: dict[str, np.ndarray], today: int) -> dict[str, float]:
    """Return the weather inputs of one alert.

    `series` has each measure of each day at the place of the alert, and `today` is the position
    of the day of the moment. The inputs "before" use only the days before that day.
    The inputs "late" are the same, with the days that the product has at the time of an alert.
    The inputs "after" use the day of the moment and the days after it: an alert cannot have them.
    """
    late_day = today - config.RISK_WEATHER_LATE_DAYS
    if late_day < max(config.RISK_RAIN_DAYS):
        raise ValueError("The weather series starts too late for this alert. Read more days.")
    after = slice(today, today + config.RISK_WEATHER_DAYS)
    late = {f"{name}_late": value for name, value in _before(series, late_day).items()}
    return (
        _before(series, today)
        | late
        | {
            "wind_after_kmh": float(series["wind_kmh"][after].max()),
            "vpd_after_kpa": float(series["vpd_kpa"][after].max()),
            "rain_after_log": float(np.log1p(series["rain_mm"][after].sum())),
        }
    )


def _before(series: dict[str, np.ndarray], today: int) -> dict[str, float]:
    rain, longest = series["rain_mm"], max(config.RISK_RAIN_DAYS)
    wet = np.flatnonzero(rain[today - longest : today] >= config.RISK_RAIN_DAY_MM)
    before = slice(today - config.RISK_WEATHER_DAYS, today)
    found = {
        name: float(np.log1p(rain[today - days : today].sum()))
        for name, days in zip(RAIN, config.RISK_RAIN_DAYS, strict=True)
    }
    return found | {
        # The days from the last day with rain: 0 if the day before the moment had rain.
        "no_rain_days_log": float(np.log1p(longest - 1 - wet[-1] if len(wet) else longest)),
        "wind_before_kmh": float(series["wind_kmh"][before].mean()),
        "vpd_before_kpa": float(series["vpd_kpa"][before].mean()),
    }
