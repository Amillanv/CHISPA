"""The growth risk of one alert: the inputs that the confidence does not have, and the answer.

The evaluation fits the models and scores them on recorded years (`evaluation/risk.py`). A live
alert gets its answer from the saved models (`risk_live.py`). The two use the functions of this
module: thus an alert of today gets its inputs, its factor and its sequence of limits from the
same code as an alert of a test. This module reads no map of the year of an alert, and it
imports no module of the evaluation. `docs/method.md` sections 11.22 and 11.24 give the rules.
"""

from pathlib import Path

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

from chispa import confidence, config, fronts, growth
from chispa.grid import layer_grid, pantanal_grid
from chispa.sources import burned, monitor

HOURS = ("hour_sin", "hour_cos", "abi_scans_log", "abi_night_scans_log", "polar_passes_log")
FIRST_HOURS = (*HOURS, "span_h_log")
RAIN = tuple(f"rain_{days}d_log" for days in config.RISK_RAIN_DAYS)
WEATHER_BEFORE = (*RAIN, "no_rain_days_log", "wind_before_kmh", "vpd_before_kpa")
WEATHER_LATE = tuple(f"{name}_late" for name in WEATHER_BEFORE)
BURNED_NEAR = tuple(f"burned_near_{years}y" for years in config.RISK_BURNED_NEAR_YEARS)
BURNED = ("burned_years_log", "burned_times", *BURNED_NEAR)
DAY_S = 86_400
# The decimals of a value in a saved file: an input of an answer, and a value of the reference.
DIGITS = 6


def key(moment: str, limit_ha: float) -> str:
    """Return the name of the model of one moment and one limit."""
    return f"{moment}h_{limit_ha:g}ha"


def first_hours_inputs(detections: dict, positions: np.ndarray) -> dict[str, float]:
    """Return how long, and at which hours, the sensors saw an alert up to the moment.

    The hour is the solar hour at the place. The GOES scans are counted by their start time:
    they say for how many periods of 10 minutes GOES saw the fire. Thus a period with a row
    from two sources, or from two GOES platforms, counts one time. Night is that of the input
    `night` of the confidence (`config.NIGHT_HOURS`).
    """
    observed = detections["observed"][positions].astype(float)
    hour = (observed / 3600 + detections["lon"][positions] / 15) % 24
    abi = detections["family"][positions] == "abi"
    dusk, dawn = config.NIGHT_HOURS
    night = (hour >= dusk) | (hour < dawn)
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


def only_inpe_goes(detections: dict, positions: np.ndarray) -> bool:
    """Return True if each detection of an alert at the moment is a GOES row of INPE."""
    family, source = detections["family"][positions], detections["source"][positions]
    return bool(((family == "abi") & (source == "inpe")).all())


def distance_m(own: tuple, other: tuple) -> np.ndarray:
    """Return the distance from each other position to the nearest position of an alert.

    Each value has the latitudes and the longitudes of a group of detections.
    """
    return cKDTree(fronts.metres(*own)).query(fronts.metres(*other))[0]


def weather_before(series: dict[str, np.ndarray], today: int) -> dict[str, float]:
    """Return the weather inputs from the days before one day.

    `series` has each measure of each day at the place of the alert, and `today` is the
    position of that day. The day itself and the later days are not read.
    """
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


def late_weather_inputs(series: dict[str, np.ndarray], today: int) -> dict[str, float]:
    """Return the weather inputs that an alert can have at its time.

    The weather product is some days late (`config.py`). Thus these inputs are those of
    `weather_before` for the day that is that number of days before the day of the moment.
    """
    late_day = today - config.RISK_WEATHER_LATE_DAYS
    if late_day < max(config.RISK_RAIN_DAYS):
        raise ValueError("The weather series starts too late for this alert. Read more days.")
    return {f"{name}_late": value for name, value in weather_before(series, late_day).items()}


def burned_layers(shares: list[np.ndarray]) -> dict[str, np.ndarray]:
    """Return the inputs of the ground that burned before, for each cell of the layer grid.

    `shares` has the burned share of each cell for each of the years before the year of the
    alerts: the oldest year first, and the year before the alerts last. A cell burned in a year
    if the share is the minimum of `config.py` or more. A cell with no burn in those years gets
    one year more than their number. The share near a cell, for more than one year, uses the
    largest share of one year for each cell: the shares of the years do not give their union.
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


def burned_share(raw_dir: Path, year: int, monitor_map: bool) -> np.ndarray:
    """Return the burned share of each cell of the layer grid for one year, from 0 to 1.

    The share is that of the annual map. `monitor_map`: if the annual map of the year is not
    on disk, the share comes from the Monitor map of that year, with the months that it has.
    As in the file of the annual map, a share is a whole number of percent.
    """
    if (raw_dir / "burned" / f"{year}.npz").exists() or not monitor_map:
        return burned.read_year(year, raw_dir)
    months, _ = monitor.read_year(year, raw_dir, pantanal_grid())
    grid, cells = layer_grid(), config.LAYER_CELLS
    # The last row and the last column of the layer grid go past the scar grid: no burn there.
    pixels = np.zeros((grid.height * cells, grid.width * cells), dtype=bool)
    pixels[: months.shape[0], : months.shape[1]] = months > 0
    share = pixels.reshape(grid.height, cells, grid.width, cells).mean(axis=(1, 3))
    return (np.round(share * 100) / 100).astype(np.float32)


def ground_before(raw_dir: Path, year: int) -> dict[str, np.ndarray]:
    """Return the inputs of the ground that burned before, for the alerts of one year.

    They read the maps of the years before that year. The annual map of a year comes in the
    next year. Thus, for a year after the test year, the map of the year before can be the
    Monitor map: `docs/method.md` section 11.35 has the check of that.
    """
    before = range(year - config.RISK_BURNED_YEARS, year)
    newest = year > config.RISK_TEST_YEAR
    shares = [burned_share(raw_dir, one, newest and one == year - 1) for one in before]
    return burned_layers(shares)


def factors(times: np.ndarray, past: dict[str, np.ndarray]) -> np.ndarray:
    """Return the factor of each alert from the known outcomes of the alerts before it.

    `past` has the time, the value and the label of the older alerts. An outcome is known if
    its alert is older than the delay, and it counts if it is in the window. The factor is the
    large alerts that came, divided by those that the values expected. The prior is added to
    the two: with few known outcomes, the factor stays near 1.
    """
    order = np.argsort(past["time"], kind="stable")
    ordered = past["time"][order]
    came = np.concatenate([[0.0], np.cumsum(past["large"][order])])
    expected = np.concatenate([[0.0], np.cumsum(past["value"][order])])
    delay = config.RISK_RECALIBRATION_DELAY_DAYS * DAY_S
    window = config.RISK_RECALIBRATION_WINDOW_DAYS * DAY_S
    newest = np.searchsorted(ordered, times - delay, side="right")
    oldest = np.searchsorted(ordered, times - window, side="right")
    prior = config.RISK_RECALIBRATION_PRIOR
    return (came[newest] - came[oldest] + prior) / (expected[newest] - expected[oldest] + prior)


def recalibrate(values: np.ndarray, factor: np.ndarray) -> np.ndarray:
    """Return the values with their odds multiplied by the factor."""
    return values * factor / (1 - values + values * factor)


def in_sequence(values: list[np.ndarray]) -> list[np.ndarray]:
    """Return the value of each alert for each limit, with no value above that of a smaller limit.

    `values` has the smallest limit first. A fire of a larger limit is also a fire of each
    smaller limit: an alert with a wrong sequence gets the smaller of the two values.
    """
    found = [values[0]]
    for value in values[1:]:
        found.append(np.minimum(found[-1], value))
    return found


def limits(saved: dict, values: dict[str, float], moment: str, at_s: float) -> list[dict]:
    """Return, for each limit of hectares, the chance, the rank and the factor of one alert.

    `saved` has the models and, for each model, the known outcomes of the older alerts as
    arrays. The chance is the value of the model after the recalibration, with no value above
    that of a smaller limit. The rank is the share of the alerts that gave the weights with a
    smaller value before the recalibration. A limit with a rank only has no chance (`config.py`).
    """
    names = [key(moment, limit) for limit in config.RISK_CLASS_LIMITS_HA]
    before, factor = [], []
    for name in names:
        model = saved["models"][name]
        row = np.array([[values[one] for one in model["inputs"]]])
        before.append(confidence.probability(model, row))
        factor.append(factors(np.array([at_s]), saved["past"][name]))
    pairs = zip(before, factor, strict=True)
    after = in_sequence([recalibrate(value, by) for value, by in pairs])
    found = []
    for place, limit in enumerate(config.RISK_CLASS_LIMITS_HA):
        reference = saved["models"][names[place]]["reference"]
        # The reference has its values with the decimals of a saved file: so has the value here.
        smaller = float(np.searchsorted(reference, round(float(before[place][0]), DIGITS)))
        rank_only = (moment, limit) in config.RISK_RANK_ONLY
        found.append(
            {
                "limit_ha": limit,
                "chance": None if rank_only else round(float(after[place][0]), 4),
                "not_tested": (moment, limit) in config.RISK_NOT_TESTED,
                "rank": round(smaller / len(reference), 3),
                "factor": round(float(factor[place][0]), 4),
            }
        )
    return found
