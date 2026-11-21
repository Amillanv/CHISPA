"""The day of each burn from the NASA product MODIS MCD64A1, through Google Earth Engine.

The burn scar map gives only a month. This product gives the day of the year that a
pixel of 463 m burned. We use it to say when a scar burned, not where.
The day comes from the change in the surface reflectance, not from a hotspot.
"""

import io
from pathlib import Path

import ee
import numpy as np

from chispa import config
from chispa.grid import Grid

ASSET = "MODIS/061/MCD64A1"


def burnday_grid() -> Grid:
    """Return the grid on which we save the burn days: the Pantanal box in coarse pixels."""
    west, south, east, north = config.PANTANAL_BOX
    pixel = config.BURNDAY_PIXEL_DEG
    return Grid(west, north, pixel, round((east - west) / pixel), round((north - south) / pixel))


def download_year(year: int, project: str, raw_dir: Path) -> list[Path]:
    """Save one file for each month of one year and return the paths.

    Earth Engine converts the product to our grid with the nearest pixel.
    """
    ee.Initialize(project=project)
    paths = []
    for month in range(1, 13):
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
    request = {
        "expression": images.first().select(["BurnDate", "Uncertainty"]).unmask(0),
        "fileFormat": "NPY",
        "grid": {
            "dimensions": {"width": grid.width, "height": grid.height},
            "affineTransform": {
                "scaleX": grid.pixel_deg,
                "shearX": 0,
                "translateX": grid.west,
                "shearY": 0,
                "scaleY": -grid.pixel_deg,
                "translateY": grid.north,
            },
            "crsCode": "EPSG:4326",
        },
    }
    tile = np.load(io.BytesIO(ee.data.computePixels(request)))
    # The product uses negative values for water and for "not mapped". We keep only burn days.
    day = np.clip(tile["BurnDate"], 0, 366).astype(np.uint16)
    return day, np.clip(tile["Uncertainty"], 0, 255).astype(np.uint8)


def read_year(year: int, raw_dir: Path) -> np.ndarray:
    """Return the burn days of one year: one layer for each month, 0 for no burn."""
    paths = [raw_dir / "burnday" / str(year) / f"{month:02d}.npz" for month in range(1, 13)]
    return np.stack([np.load(path)["day"] for path in paths])


def scar_burn_days(
    numbers: np.ndarray, months: np.ndarray, fine: Grid, days: np.ndarray, coarse: Grid, count: int
) -> tuple[np.ndarray, np.ndarray]:
    """Return the first and the last burn day of each scar number. 0 means "no burn day".

    For each pixel of a scar we read the burn day of the scar month.
    If that month has no burn day, we read the months before it (`config.py` gives how many).
    The burn scar map frequently gives a month that is later than the burn.
    """
    rows, cols = np.nonzero(numbers)
    scar = numbers[rows, cols]
    month = months[rows, cols].astype(int)
    lats, lons = fine.lats()[rows], fine.lons()[cols]
    coarse_rows, coarse_cols = coarse.rows_cols(lats, lons)
    inside = (
        (coarse_rows >= 0)
        & (coarse_rows < coarse.height)
        & (coarse_cols >= 0)
        & (coarse_cols < coarse.width)
    )
    scar, month = scar[inside], month[inside]
    coarse_rows, coarse_cols = coarse_rows[inside], coarse_cols[inside]
    day = np.zeros(len(scar), dtype=int)
    for back in range(config.EVAL_MONTHS_BEFORE + 1):
        layer = month - 1 - back
        usable = (day == 0) & (layer >= 0)
        day[usable] = days[layer[usable], coarse_rows[usable], coarse_cols[usable]]
    known = day > 0
    first = np.full(count + 1, 999)
    last = np.zeros(count + 1, dtype=int)
    np.minimum.at(first, scar[known], day[known])
    np.maximum.at(last, scar[known], day[known])
    first[first == 999] = 0
    return first, last
