"""Inputs of the growth risk for the state of the season and of the ground.

The share of the alerts that become large changes with the year, and the inputs of the confidence
do not have the state of the season. This module gives each alert the candidate inputs for it:
the dryness fields of INPE, the first hours of the alert, the weather, the ground that burned
in the years before, and the river level. `docs/method.md` section 11.22 gives the rules.
"""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np

from chispa import config
from chispa.evaluation.match import Fields
from chispa.evaluation.risk_mark import near_earlier
from chispa.grid import layer_grid
from chispa.risk import (
    BURNED,
    FIRST_HOURS,
    WEATHER_BEFORE,
    WEATHER_LATE,
    first_hours_inputs,
    ground_before,
    late_weather_inputs,
    only_inpe_goes,
    weather_before,
)
from chispa.sources import inpe, weather

DRYNESS = ("dry_days_log", "rain_mm_log", "fire_risk", "no_dryness", "no_fire_risk")
CALENDAR = ("season_sin", "season_cos")
WEATHER_AFTER = ("wind_after_kmh", "vpd_after_kpa", "rain_after_log")
EXPOSURE = ("people_log", "protected_km_log", "indigenous_km_log")
RIVER = ("river_m", "river_change_m")
# The sets of inputs that the table `risk_inputs` compares. A set has a name, the inputs that
# it adds to the inputs of now, and the inputs of now that it removes.
# The inputs that the models have and the confidence does not have: the groups that passed the
# rule. The weather is the late weather: an alert can have it at its time. The ground that
# burned before passed on 2026-11-26, with the level after the recalibration.
# Each set below is a change of the inputs of now. For a set with a name that starts with
# "without", the inputs of now are tested against the set. For each other set, the set is tested.
ADOPTED = FIRST_HOURS + WEATHER_LATE + BURNED
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
    "without burned before": ((), BURNED),
    "with river level": (RIVER, ()),
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


def add_model_inputs(
    rows: list[dict], detections: Fields, raw_dir: Path, year: int, last: date
) -> None:
    """Give each row of one year the inputs of the models that the confidence does not have.

    They are the first hours, the weather and the ground that burned before. A row also gets
    the mark of an alert with only GOES rows of INPE, and that of an alert near an earlier
    alert. `last` is the last day of the weather that the rows need.
    """
    # The weather inputs need more than 90 days before an alert and some days after its moment.
    start, grid = date(year - 1, 9, 1), weather.weather_grid()
    days = weather.read_days(raw_dir, start, last)
    # The ground that burned before comes from the maps of the years before the year only.
    ground, cells = ground_before(raw_dir, year), layer_grid()
    for row, mark in zip(rows, near_earlier(rows, detections), strict=True):
        positions = row["positions"]
        row["only_inpe_goes"], row["near_earlier"] = only_inpe_goes(detections, positions), mark
        row["inputs"] |= first_hours_inputs(detections, positions)
        place = detections["lat"][positions].mean(), detections["lon"][positions].mean()
        cell = tuple(int(index) for index in grid.rows_cols(*place))
        day = datetime.fromtimestamp(row["at"], UTC).date()
        series = {name: layers[:, cell[0], cell[1]] for name, layers in days.items()}
        row["inputs"] |= weather_inputs(series, (day - start).days)
        spot = tuple(int(index) for index in cells.rows_cols(*place))
        row["inputs"] |= {name: float(layer[spot]) for name, layer in ground.items()}


def weather_inputs(series: dict[str, np.ndarray], today: int) -> dict[str, float]:
    """Return the weather inputs of one alert.

    `series` has each measure of each day at the place of the alert, and `today` is the position
    of the day of the moment. The inputs "before" use only the days before that day.
    The inputs "late" are the same, with the days that the product has at the time of an alert.
    The inputs "after" use the day of the moment and the days after it: an alert cannot have them.
    """
    late = late_weather_inputs(series, today)
    after = slice(today, today + config.RISK_WEATHER_DAYS)
    return (
        weather_before(series, today)
        | late
        | {
            "wind_after_kmh": float(series["wind_kmh"][after].max()),
            "vpd_after_kpa": float(series["vpd_kpa"][after].max()),
            "rain_after_log": float(np.log1p(series["rain_mm"][after].sum())),
        }
    )


def river_inputs(levels: dict[date, float], day: date) -> dict[str, float]:
    """Return the river inputs of one alert: the level of the day before the day of the moment,
    and its change in the days before that day. The levels are in metres."""
    before = day - timedelta(days=1)
    earlier = before - timedelta(days=config.RISK_RIVER_CHANGE_DAYS)
    for needed in (before, earlier):
        if needed not in levels:
            raise ValueError(
                f"The river has no level for {needed}. "
                f"Run `chispa fetch river --year {needed.year}`, or wait for the data of ANA."
            )
    return {"river_m": levels[before], "river_change_m": levels[before] - levels[earlier]}
