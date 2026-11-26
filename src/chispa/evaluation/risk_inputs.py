"""Inputs of the growth risk for the state of the season and of the ground.

The share of the alerts that become large changes with the year, and the inputs of the confidence
do not have the state of the season. This module gives each alert the candidate inputs for it:
the dryness fields of INPE, the first hours of the alert, the weather, the ground that burned
in the years before, and the river level. `docs/method.md` section 11.22 gives the rules.
"""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
from scipy import ndimage

from chispa import config, growth
from chispa.evaluation.match import Fields
from chispa.grid import layer_grid
from chispa.sources import burned, inpe, weather

DRYNESS = ("dry_days_log", "rain_mm_log", "fire_risk", "no_dryness", "no_fire_risk")
HOURS = ("hour_sin", "hour_cos", "abi_scans_log", "abi_night_scans_log", "polar_passes_log")
FIRST_HOURS = (*HOURS, "span_h_log")
CALENDAR = ("season_sin", "season_cos")
RAIN = tuple(f"rain_{days}d_log" for days in config.RISK_RAIN_DAYS)
WEATHER_BEFORE = (*RAIN, "no_rain_days_log", "wind_before_kmh", "vpd_before_kpa")
WEATHER_AFTER = ("wind_after_kmh", "vpd_after_kpa", "rain_after_log")
WEATHER_LATE = tuple(f"{name}_late" for name in WEATHER_BEFORE)
EXPOSURE = ("people_log", "protected_km_log", "indigenous_km_log")
BURNED_NEAR = tuple(f"burned_near_{years}y" for years in config.RISK_BURNED_NEAR_YEARS)
BURNED = ("burned_years_log", "burned_times", *BURNED_NEAR)
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


def add_model_inputs(
    rows: list[dict], detections: Fields, raw_dir: Path, year: int, last: date
) -> None:
    """Give each row of one year the inputs of the models that the confidence does not have.

    They are the first hours, the weather and the ground that burned before. A row also gets
    the mark of an alert with only GOES rows of INPE. `last` is the last day of the weather
    that the rows need.
    """
    # The weather inputs need more than 90 days before an alert and some days after its moment.
    start, grid = date(year - 1, 9, 1), weather.weather_grid()
    days = weather.read_days(raw_dir, start, last)
    # The ground that burned before comes from the maps of the years before the year only.
    before = range(year - config.RISK_BURNED_YEARS, year)
    ground, cells = burned_layers([burned.read_year(one, raw_dir) for one in before]), layer_grid()
    for row in rows:
        positions = row["positions"]
        family, source = detections["family"][positions], detections["source"][positions]
        row["only_inpe_goes"] = bool(((family == "abi") & (source == "inpe")).all())
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


def burned_layers(shares: list[np.ndarray]) -> dict[str, np.ndarray]:
    """Return the inputs of the ground that burned before, for each cell of the layer grid.

    `shares` has the burned share of each cell for each of the years before the year of the
    alerts: the oldest year first, and the year before the alerts last. A cell burned in a year
    if the share is the minimum of `config.py` or more. A cell with no burn in those years gets
    one year more than their number.
    """
    burned = np.stack(shares) >= config.RISK_BURNED_CELL_SHARE
    # From the newest year to the oldest, the first year with a burn: 1 is the year before.
    years = np.where(burned.any(axis=0), burned[::-1].argmax(axis=0) + 1, len(shares) + 1)
    layers = {"burned_years_log": np.log(years), "burned_times": burned.sum(axis=0).astype(float)}
    side = config.RISK_BURNED_NEAR_CELLS
    for name, count in zip(BURNED_NEAR, config.RISK_BURNED_NEAR_YEARS, strict=True):
        largest = np.max(shares[-count:], axis=0).astype(float)
        # The filter can give a very small negative number where no ground burned.
        layers[name] = np.clip(ndimage.uniform_filter(largest, size=side, mode="constant"), 0, 1)
    return layers


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
