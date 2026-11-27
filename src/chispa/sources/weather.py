"""The weather of each day from ERA5-Land, through Google Earth Engine.

Wind, rain and dry air are the usual causes of a fire that grows, and the share of the alerts
that become large changes with the year. ERA5-Land is a record of the weather of each hour on
a grid of approximately 11 km. We save four measures of each day on that grid.
A second file has the wind with its direction, for each block of 6 hours: a fire front goes
where the wind goes, and the largest speed of a day does not say where that is.
It is a record of the past, not a forecast: a day is in the product some days after it.
"""

from calendar import monthrange
from datetime import date
from pathlib import Path

import ee
import numpy as np

from chispa import config
from chispa.earthengine import again, read_window
from chispa.grid import Grid

ASSET = "ECMWF/ERA5_LAND/HOURLY"
# The largest wind speed, dryness of the air and temperature of a day, and its sum of rain.
# A day is a UTC day.
MEASURES = ("wind_kmh", "vpd_kpa", "temp_c", "rain_mm")
NO_VALUE = -9999.0  # A cell of water has no value in the product.
# The wind of a block: where the air goes, to the east and to the north, and its mean speed.
# The two parts are means of the hours: a wind that turns in a block gives a short arrow.
WIND = ("east_kmh", "north_kmh", "speed_kmh")
BLOCK_HOURS = 6  # A UTC day has four blocks. The first starts at 00:00.
PART = ".part"  # The end of the name of the file of a month in progress (`bucket.source_files`).


def weather_grid() -> Grid:
    """Return the cells of the product over the Pantanal box. A cell has its centre at a
    whole tenth of a degree, thus the box edge is a centre and Earth Engine changes no value."""
    west, south, east, north = config.PANTANAL_BOX
    pixel = config.WEATHER_PIXEL_DEG
    width, height = round((east - west) / pixel) + 1, round((north - south) / pixel) + 1
    return Grid(west - pixel / 2, north + pixel / 2, pixel, width, height)


def download_year(year: int, project: str, raw_dir: Path) -> list[Path]:
    """Save one file for each complete month of one year and return the paths.

    A file has one layer for each day of the month, for each measure. A day is complete if the
    product has its last hour. A month in progress gets a file with its complete days.
    """
    ee.Initialize(project=project)
    recent = ee.ImageCollection(ASSET).filterDate(f"{year}-01-01", f"{year + 1}-01-01")
    newest = ee.Date(recent.aggregate_max("system:time_start")).format("YYYY-MM-dd HH").getInfo()
    paths = []
    for month in range(1, 13):
        days = monthrange(year, month)[1]
        complete = sum(f"{year}-{month:02d}-{day:02d} 23" <= newest for day in range(1, days + 1))
        if complete:
            paths += _save_month(raw_dir, date(year, month, complete), complete == days)
        if complete < days:
            break
    return paths


def _save_month(raw_dir: Path, last: date, complete: bool) -> list[Path]:
    """Save the measures file and the wind file of one month, to the day `last`.

    The file of a month in progress has a name that ends in `.part`: it is not a raw file yet,
    and it does not go to the bucket. Each fetch makes it again. Return the complete files.
    """
    paths = []
    for kind, get in (("weather", _get_day), ("wind", _get_wind)):
        path = raw_dir / kind / str(last.year) / f"{last.month:02d}.npz"
        part = path.with_name(path.name + PART)
        if not path.exists():
            layers = [get(last.replace(day=day)) for day in range(1, last.day + 1)]
            if kind == "wind":
                stacked = {"wind": np.concatenate(layers)}
            else:
                stacked = {name: np.stack([layer[name] for layer in layers]) for name in MEASURES}
            path.parent.mkdir(parents=True, exist_ok=True)
            with (path if complete else part).open("wb") as file:
                np.savez_compressed(file, **stacked)
        if complete:
            part.unlink(missing_ok=True)
            paths.append(path)
    return paths


def _get_day(day: date) -> dict[str, np.ndarray]:
    grid, start = weather_grid(), ee.Date(day.isoformat())
    hours = ee.ImageCollection(ASSET).filterDate(start, start.advance(1, "day")).map(_measures)
    image = hours.select(list(MEASURES[:3])).max().addBands(hours.select(MEASURES[3]).sum())
    tile = again(
        lambda: read_window(image.unmask(NO_VALUE), grid, (0, 0), (grid.width, grid.height))
    )
    layers = {name: tile[name].astype(np.float32) for name in MEASURES}
    return {name: np.where(layer <= NO_VALUE, np.nan, layer) for name, layer in layers.items()}


def _get_wind(day: date) -> np.ndarray:
    """Return the wind of one day: one layer for each block and each part of `WIND`."""
    grid, start, bands = weather_grid(), ee.Date(day.isoformat()), []
    for block in range(24 // BLOCK_HOURS):
        first = start.advance(block * BLOCK_HOURS, "hour")
        hours = ee.ImageCollection(ASSET).filterDate(first, first.advance(BLOCK_HOURS, "hour"))
        parts = hours.select(["u_component_of_wind_10m", "v_component_of_wind_10m"]).mean()
        speed = hours.map(lambda hour: _measures(hour).select(MEASURES[0])).mean()
        # Metres for each second to km/h. The speed of `_measures` is in km/h.
        bands.append(
            parts.multiply(3.6).addBands(speed).rename([f"{name}{block}" for name in WIND])
        )
    image = ee.Image.cat(bands).unmask(NO_VALUE)
    tile = again(lambda: read_window(image, grid, (0, 0), (grid.width, grid.height)))
    layers = np.array(
        [[tile[f"{name}{block}"] for name in WIND] for block in range(len(bands))], dtype=np.float32
    )
    return np.where(layers <= NO_VALUE, np.nan, layers)


def _measures(hour: ee.Image) -> ee.Image:
    """Return the four measures of one hour, in our units."""
    east, north = hour.select("u_component_of_wind_10m"), hour.select("v_component_of_wind_10m")
    wind = east.pow(2).add(north.pow(2)).sqrt().multiply(3.6)  # Metres for each second to km/h.
    celsius = hour.select("temperature_2m").subtract(273.15)
    dew = hour.select("dewpoint_temperature_2m").subtract(273.15)
    # The dryness of the air is the vapour pressure deficit: the pressure of a full air at this
    # temperature minus the pressure of the vapour that the air has, in kilopascals (Tetens).
    dryness = _vapour_kpa(celsius).subtract(_vapour_kpa(dew))
    rain = hour.select("total_precipitation_hourly").multiply(1000)  # Metres to millimetres.
    bands = [wind, dryness, celsius, rain]
    return ee.Image.cat(bands).rename(list(MEASURES))


def _vapour_kpa(celsius: ee.Image) -> ee.Image:
    return celsius.multiply(17.27).divide(celsius.add(237.3)).exp().multiply(0.6108)


def read_days(raw_dir: Path, first: date, last: date) -> dict[str, np.ndarray]:
    """Return each measure for the days from `first` to `last`: days, rows and columns.

    The files of each month of those days must be on disk.
    """
    found: dict[str, list] = {name: [] for name in MEASURES}
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        path = raw_dir / "weather" / str(year) / f"{month:02d}.npz"
        if not path.exists():
            raise RuntimeError(f"Run `chispa fetch weather --year {year}` first.")
        file = np.load(path)
        for name in MEASURES:
            found[name].append(file[name])
        year, month = (year, month + 1) if month < 12 else (year + 1, 1)
    start = (first - date(first.year, first.month, 1)).days
    count = (last - first).days + 1
    return {name: np.concatenate(parts)[start : start + count] for name, parts in found.items()}


def read_part(raw_dir: Path, month: date) -> tuple[dict[str, np.ndarray], np.ndarray] | None:
    """Return the complete days of a month in progress: each measure, and the wind blocks.

    None: the month of the day `month` has no such files. `chispa fetch weather` makes them.
    """
    file = f"{month.month:02d}.npz{PART}"
    days, wind = (raw_dir / kind / str(month.year) / file for kind in ("weather", "wind"))
    if not (days.exists() and wind.exists()):
        return None
    saved = np.load(days)
    return {name: saved[name] for name in MEASURES}, np.load(wind)["wind"]


def read_wind(raw_dir: Path, first: date, last: date) -> np.ndarray:
    """Return the wind of the blocks from the day `first` to the day `last`, in time sequence:
    blocks, the parts of `WIND`, rows and columns. The files of each month must be on disk."""
    found, year, month = [], first.year, first.month
    while (year, month) <= (last.year, last.month):
        path = raw_dir / "wind" / str(year) / f"{month:02d}.npz"
        if not path.exists():
            raise RuntimeError(f"Run `chispa fetch weather --year {year}` first.")
        found.append(np.load(path)["wind"])
        year, month = (year, month + 1) if month < 12 else (year + 1, 1)
    each_day = 24 // BLOCK_HOURS
    start = (first - date(first.year, first.month, 1)).days * each_day
    return np.concatenate(found)[start : start + ((last - first).days + 1) * each_day]
