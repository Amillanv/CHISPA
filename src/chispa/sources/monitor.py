"""The monthly burned area of MapBiomas Monitor do Fogo, through Google Earth Engine.

The annual map of burn scars comes in the next year. This map comes some weeks after each month.
It is a candidate for the burned ground of an event, and a reference for a year with no annual map.
"""

import json
import re
from datetime import datetime
from pathlib import Path

import ee
import numpy as np

from chispa import config
from chispa.earthengine import again, read_window
from chispa.grid import Grid

ASSET = "projects/mapbiomas-public/assets/brazil/fire/monitor/mapbiomas_fire_monthly_burned_v1"
SCALE_M = 30  # The pixel size of the images of the asset.
TILE_NAME = re.compile(r"r(\d+)_c(\d+)\.npz")

Box = tuple[float, float, float, float]  # south, west, north, east


def month_names(first: datetime, last: datetime) -> list[str]:
    """Return the image name of each month from the first detection to the months after the last."""
    year, month = first.year, first.month
    end = last.year * 12 + last.month + config.MONITOR_MONTHS_AFTER
    names = []
    while year * 12 + month <= end:
        names.append(f"brazil-{year}-{month}")
        year, month = (year, month + 1) if month < 12 else (year + 1, 1)
    return names


def burned_ha(box: Box, first: datetime, last: datetime) -> float:
    """Return the hectares of a box that the map gives as burned in the months of an event."""
    south, west, north, east = box
    region = ee.Geometry.Rectangle([west, south, east, north])  # Earth Engine uses lon, lat.
    months = ee.ImageCollection(ASSET).filter(ee.Filter.inList("name", month_names(first, last)))
    burned = months.map(lambda image: image.unmask(0).gt(0)).max()
    area = ee.Image.pixelArea().divide(10_000).updateMask(burned).rename("burned")
    found = area.reduceRegion(ee.Reducer.sum(), region, SCALE_M, maxPixels=1e9).getInfo()
    return round(float(found.get("burned") or 0), 2)


def image_times(project: str) -> dict[str, str]:
    """Return the time of the last change of each month image of the asset, by its name."""
    ee.Initialize(project=project)
    images = ee.data.listAssets({"parent": ASSET, "pageSize": 1000})["assets"]
    return {image["name"].rsplit("/", 1)[-1]: image["updateTime"] for image in images}


def months_on_disk(year: int, raw_dir: Path) -> int:
    """Return the last month of one year that the saved map has. 0: the year has no folder."""
    folders = sorted((raw_dir / "monitor").glob(f"{year}-[0-9][0-9]"))
    return int(folders[-1].name[-2:]) if folders else 0


def download_year(year: int, project: str, raw_dir: Path, grid: Grid) -> list[Path]:
    """Save the map of one year as tiles and return the paths.

    A pixel holds the first month of the year in which the map gives it as burned, or 0.
    The folder name has the last month that the map had: a year in progress gets a new
    folder when the map has one more month, and a folder never changes. The file
    `published.json` has the time of the last change of each month image.
    """
    changed = image_times(project)
    months = [month for month in range(1, 13) if f"brazil-{year}-{month}" in changed]
    if not months:
        raise RuntimeError(f"The Monitor map has no month of {year}.")
    layers = []
    for month in months:
        image = ee.ImageCollection(ASSET).filter(ee.Filter.eq("name", f"brazil-{year}-{month}"))
        layers.append(image.first().select(0).gt(0).selfMask().multiply(month).toUint8())
    first = ee.ImageCollection(layers).min().unmask(0).toUint8()
    folder, side, paths = raw_dir / "monitor" / f"{year}-{max(months):02d}", config.SCAR_TILE_PX, []
    for row in range(0, grid.height, side):
        for col in range(0, grid.width, side):
            path = folder / f"r{row:05d}_c{col:05d}.npz"
            if not path.exists():
                size = (min(side, grid.width - col), min(side, grid.height - row))
                tile = again(lambda at=(row, col), size=size: read_window(first, grid, at, size))
                path.parent.mkdir(parents=True, exist_ok=True)
                np.savez_compressed(path, month=tile[tile.dtype.names[0]].astype(np.uint8))
            paths.append(path)
    times = folder / "published.json"
    if not times.exists():
        found = {month: changed[f"brazil-{year}-{month}"] for month in months}
        times.write_text(json.dumps(found, indent=1))
    return paths


def read_year(year: int, raw_dir: Path, grid: Grid) -> tuple[np.ndarray, int]:
    """Return the month grid of one year, and the last month that the map had.

    With more than one folder for the year, the folder with the newest month is read.
    """
    folders = sorted((raw_dir / "monitor").glob(f"{year}-[0-9][0-9]"))
    if not folders:
        raise RuntimeError(f"Run `chispa fetch monitor --year {year}` first.")
    months = np.zeros((grid.height, grid.width), dtype=np.uint8)
    covered = 0
    for path in sorted(folders[-1].glob("r*_c*.npz")):
        row, col = (int(text) for text in TILE_NAME.fullmatch(path.name).groups())
        tile = np.load(path)["month"]
        months[row : row + tile.shape[0], col : col + tile.shape[1]] = tile
        covered += tile.size
    if covered != months.size:
        raise RuntimeError(f"The Monitor tiles of {year} do not cover the grid. Run fetch again.")
    return months, int(folders[-1].name[-2:])


def read_published(year: int, raw_dir: Path) -> dict[int, datetime]:
    """Return, for each month of the map of one year, the time when its image last changed.

    An image that did not change after its first day in the asset has the time when the map
    of that month came. The newest folder of the year has the file.
    """
    folders = sorted((raw_dir / "monitor").glob(f"{year}-[0-9][0-9]"))
    if not folders or not (folders[-1] / "published.json").exists():
        raise RuntimeError(f"Run `chispa fetch monitor --year {year}` first.")
    found = json.loads((folders[-1] / "published.json").read_text())
    return {int(month): datetime.fromisoformat(time) for month, time in found.items()}
