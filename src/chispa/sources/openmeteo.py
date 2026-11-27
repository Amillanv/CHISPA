"""The weather of the newest days from Open-Meteo, for a live forecast.

ERA5-Land is approximately 6 days late (`weather.py`), and a forecast for a look of today needs
the weather of the days before that look. Open-Meteo gives each hour of the IFS model of ECMWF to
the present day, with no key. This module gets those hours for some cells of our weather grid,
saves each answer as a raw file, and makes the measures of `weather.py` from it: four measures
of each day, and the wind of each block of 6 hours.
IFS is a different model: its levels are not those of ERA5-Land (`docs/sources.md` section 8.4).
"""

import json
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import requests

from chispa.sources.weather import BLOCK_HOURS, MEASURES

API = "https://archive-api.open-meteo.com/v1/archive"
MODEL = "ecmwf_ifs"
# The hourly fields that we read, with the unit that the answer must give for each.
FIELDS = {
    "temperature_2m": "°C",
    "dew_point_2m": "°C",
    "wind_speed_10m": "km/h",
    "wind_direction_10m": "°",
    "precipitation": "mm",
}


def download(lats: np.ndarray, lons: np.ndarray, days: tuple[date, date], raw_dir: Path) -> Path:
    """Get the hours of the days from the first to the last for some positions, and save them.

    The file has the answer as Open-Meteo gave it. Its name has the time of the request: an
    answer for a recent day can change, thus each request makes a new file.
    """
    params = {
        "latitude": ",".join(f"{value:.2f}" for value in lats),
        "longitude": ",".join(f"{value:.2f}" for value in lons),
        "start_date": days[0].isoformat(),
        "end_date": days[1].isoformat(),
        "hourly": ",".join(FIELDS),
        "models": MODEL,
        "timezone": "GMT",
    }
    answer = requests.get(API, params=params, timeout=120)
    if answer.status_code != 200:
        raise RuntimeError(f"Open-Meteo gave the status {answer.status_code}. Try again later.")
    path = raw_dir / "openmeteo" / f"{datetime.now(UTC):%Y-%m-%dT%H%M%S}.json"
    if path.exists():
        raise RuntimeError(f"{path} exists: a raw file does not change. Try again in a second.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(answer.text)
    return path


def read(path: Path) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """Return the weather of a saved answer, for each position in the sequence of the request.

    The first value has each measure of `weather.py`: positions, days. The second has the wind
    of each block: positions, blocks, the three parts of `weather.WIND`.
    """
    found = json.loads(path.read_text())
    positions = found if isinstance(found, list) else [found]
    days = {name: [] for name in MEASURES}
    wind = []
    for position in positions:
        of_day, blocks = _measures(position, path)
        for name in MEASURES:
            days[name].append(of_day[name])
        wind.append(blocks)
    return {name: np.array(values) for name, values in days.items()}, np.array(wind)


def _hours(position: dict, path: Path) -> dict[str, np.ndarray]:
    """Return each field of one position as days x 24 hours, after a check of the answer."""
    units, hourly = position.get("hourly_units", {}), position.get("hourly", {})
    values = {}
    for name, unit in FIELDS.items():
        if units.get(name) != unit:
            raise ValueError(f"{path}: {name} has the unit {units.get(name)}, not {unit}.")
        series = hourly[name]
        if len(series) % 24 or None in series:
            raise ValueError(f"{path}: {name} has an hour with no value, or a part day.")
        values[name] = np.array(series, dtype=float).reshape(-1, 24)
    if not hourly["time"][0].endswith("T00:00") or position.get("utc_offset_seconds") != 0:
        raise ValueError(f"{path}: the hours are not UTC days from 00:00.")
    return values


def _measures(position: dict, path: Path) -> tuple[dict[str, np.ndarray], np.ndarray]:
    value = _hours(position, path)
    speed = value["wind_speed_10m"]
    dryness = _vapour_kpa(value["temperature_2m"]) - _vapour_kpa(value["dew_point_2m"])
    of_day = {
        "wind_kmh": speed.max(axis=1),
        "vpd_kpa": dryness.max(axis=1),
        "temp_c": value["temperature_2m"].max(axis=1),
        "rain_mm": value["precipitation"].sum(axis=1),
    }
    # The direction of Open-Meteo is where the wind comes from. `weather.py` has where the air goes.
    toward = np.deg2rad(value["wind_direction_10m"] + 180)
    parts = [speed * np.sin(toward), speed * np.cos(toward), speed]
    blocks = [part.reshape(-1, BLOCK_HOURS).mean(axis=1) for part in parts]
    return of_day, np.column_stack(blocks)


def _vapour_kpa(celsius: np.ndarray) -> np.ndarray:
    """Return the pressure of a full air at a temperature, with the formula of `weather.py`."""
    return 0.6108 * np.exp(17.27 * celsius / (celsius + 237.3))
