"""The day of each burn from the NASA product MODIS MCD64A1, through Google Earth Engine.

The burn scar map gives only a month. This product gives the day of the year that a
pixel of 463 m burned. We use it to say when a fire burned, not where.
The day comes from the change in the surface reflectance, not from a hotspot.
"""

from datetime import UTC, datetime
from pathlib import Path

import ee
import numpy as np

from chispa import config
from chispa.earthengine import read_window
from chispa.grid import Grid

ASSET = "MODIS/061/MCD64A1"


def burnday_grid() -> Grid:
    """Return the grid on which we save the burn days: the Pantanal box in coarse pixels."""
    west, south, east, north = config.PANTANAL_BOX
    pixel = config.BURNDAY_PIXEL_DEG
    return Grid(west, north, pixel, round((east - west) / pixel), round((north - south) / pixel))


def download_year(year: int, project: str, raw_dir: Path) -> list[Path]:
    """Save one file for each month of one year that the product has, and return the paths.

    Earth Engine converts the product to our grid with the nearest pixel.
    """
    ee.Initialize(project=project)
    newest = ee.Date(ee.ImageCollection(ASSET).aggregate_max("system:time_start"))
    newest, paths = newest.format("YYYY-MM").getInfo(), []
    for month in range(1, 13):
        if f"{year}-{month:02d}" > newest:
            break
        path = raw_dir / "burnday" / str(year) / f"{month:02d}.npz"
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            day, uncertainty = _get_month(year, month)
            np.savez_compressed(path, day=day, uncertainty=uncertainty)
        paths.append(path)
    return paths


def _get_month(year: int, month: int) -> tuple[np.ndarray, np.ndarray]:
    grid = burnday_grid()
    start = ee.Date.fromYMD(year, month, 1)
    images = ee.ImageCollection(ASSET).filterDate(start, start.advance(1, "month"))
    if images.size().getInfo() != 1:
        raise RuntimeError(f"MCD64A1 has no single image for {year}-{month:02d}.")
    bands = images.first().select(["BurnDate", "Uncertainty"]).unmask(0)
    tile = read_window(bands, grid, (0, 0), (grid.width, grid.height))
    # The product uses negative values for water and for "not mapped". We keep only burn days.
    day = np.clip(tile["BurnDate"], 0, 366).astype(np.uint16)
    return day, np.clip(tile["Uncertainty"], 0, 255).astype(np.uint8)


def read_year(year: int, raw_dir: Path) -> np.ndarray:
    """Return the burn days of one year: one layer for each month, 0 for no burn.

    A year in progress has no file for its last months: those layers have no burn day.
    """
    paths = [raw_dir / "burnday" / str(year) / f"{month:02d}.npz" for month in range(1, 13)]
    have = [path.exists() for path in paths]
    complete = all(have) or (year == datetime.now(UTC).year and have == sorted(have, reverse=True))
    if not have[0] or not complete:
        raise RuntimeError(f"Run `chispa fetch burnday --year {year}` first.")
    layers = [np.load(path)["day"] for path, there in zip(paths, have, strict=True) if there]
    return np.stack(layers + [np.zeros_like(layers[0])] * (12 - len(layers)))
