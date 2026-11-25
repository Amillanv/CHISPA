"""The weather of each day from ERA5-Land, through Google Earth Engine.

Wind, rain and dry air are the usual causes of a fire that grows, and the share of the alerts
that become large changes with the year. ERA5-Land is a record of the weather of each hour on
a grid of approximately 11 km. We save four measures of each day on that grid.
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


def weather_grid() -> Grid:
    """Return the cells of the product over the Pantanal box. A cell has its centre at a
    whole tenth of a degree, thus the box edge is a centre and Earth Engine changes no value."""
    west, south, east, north = config.PANTANAL_BOX
    pixel = config.WEATHER_PIXEL_DEG
    width, height = round((east - west) / pixel) + 1, round((north - south) / pixel) + 1
    return Grid(west - pixel / 2, north + pixel / 2, pixel, width, height)


def download_year(year: int, project: str, raw_dir: Path) -> list[Path]:
    """Save one file for each complete month of one year and return the paths.

    A file has one layer for each day of the month, for each measure. A month is complete
    if the product has its last hour: a month in progress gets no file.
    """
    ee.Initialize(project=project)
    recent = ee.ImageCollection(ASSET).filterDate(f"{year}-01-01", f"{year + 1}-01-01")
    newest = ee.Date(recent.aggregate_max("system:time_start")).format("YYYY-MM-dd HH").getInfo()
    paths = []
    for month in range(1, 13):
        days = monthrange(year, month)[1]
        if f"{year}-{month:02d}-{days:02d} 23" > newest:
            break
        path = raw_dir / "weather" / str(year) / f"{month:02d}.npz"
        if not path.exists():
            layers = [_get_day(date(year, month, day)) for day in range(1, days + 1)]
            path.parent.mkdir(parents=True, exist_ok=True)
            stacked = {name: np.stack([layer[name] for layer in layers]) for name in MEASURES}
            np.savez_compressed(path, **stacked)
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
