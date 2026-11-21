"""MapBiomas Fogo burn scars through Google Earth Engine.

The burn scars are the ground truth of the evaluation: they say where a fire burned.
The map is a grid: each pixel holds 0, or the month (1 to 12) of the burn.
`fetch` saves the grid of one year as tiles. `build` groups the burned pixels into scars,
then `fires.py` groups the scars into fires.
"""

import io
import re
from pathlib import Path

import ee
import numpy as np
from scipy import ndimage

from chispa import config
from chispa.grid import Grid

TILE_NAME = re.compile(r"r(\d+)_c(\d+)\.npz")


def check_access(project: str) -> list[str]:
    """Return the band names for the development year and the test year.

    Earth Engine uses the Google login on this computer. README.md gives the setup.
    """
    ee.Initialize(project=project)
    available = ee.Image(config.SCAR_ASSET).bandNames().getInfo()
    wanted = [f"burned_monthly_{year}" for year in (config.DEVELOPMENT_YEAR, config.TEST_YEAR)]
    absent = [name for name in wanted if name not in available]
    if absent:
        raise RuntimeError(f"The MapBiomas asset has no band {absent}.")
    return wanted


def download_year(year: int, project: str, raw_dir: Path, grid: Grid) -> list[Path]:
    """Save the month grid of one year as tiles and return the paths."""
    ee.Initialize(project=project)
    image = ee.Image(config.SCAR_ASSET).select(f"burned_monthly_{year}").unmask(0)
    paths = []
    for row in range(0, grid.height, config.SCAR_TILE_PX):
        for col in range(0, grid.width, config.SCAR_TILE_PX):
            path = raw_dir / "scars" / str(year) / f"r{row:05d}_c{col:05d}.npz"
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                np.savez_compressed(path, month=_get_tile(image, grid, row, col))
            paths.append(path)
    return paths


def _get_tile(image: ee.Image, grid: Grid, row: int, col: int) -> np.ndarray:
    height = min(config.SCAR_TILE_PX, grid.height - row)
    width = min(config.SCAR_TILE_PX, grid.width - col)
    request = {
        "expression": image,
        "fileFormat": "NPY",
        "grid": {
            "dimensions": {"width": width, "height": height},
            "affineTransform": {
                "scaleX": grid.pixel_deg,
                "shearX": 0,
                "translateX": grid.west + col * grid.pixel_deg,
                "shearY": 0,
                "scaleY": -grid.pixel_deg,
                "translateY": grid.north - row * grid.pixel_deg,
            },
            "crsCode": "EPSG:4326",
        },
    }
    tile = np.load(io.BytesIO(ee.data.computePixels(request)))
    return tile[tile.dtype.names[0]].astype(np.uint8)


def read_year(year: int, raw_dir: Path, grid: Grid) -> np.ndarray:
    """Join the tiles of one year into one month grid."""
    paths = sorted((raw_dir / "scars" / str(year)).glob("r*_c*.npz"))
    months = np.zeros((grid.height, grid.width), dtype=np.uint8)
    covered = 0
    for path in paths:
        row, col = (int(text) for text in TILE_NAME.fullmatch(path.name).groups())
        tile = np.load(path)["month"]
        months[row : row + tile.shape[0], col : col + tile.shape[1]] = tile
        covered += tile.size
    if covered != months.size:
        raise RuntimeError(f"The scar tiles of {year} do not cover the grid. Run fetch again.")
    return months


def find_scars(months: np.ndarray) -> np.ndarray:
    """Return a grid that holds the scar number of each pixel (0 for no scar).

    A scar is a group of pixels that touch and that have the same month.
    """
    # This function holds a full year of pixels in memory: some gigabytes.
    # Rumour says that Sam Altman wants idle local RAM put to work. You are welcome, Sam.
    numbers = np.zeros(months.shape, dtype=np.int32)
    links = ndimage.generate_binary_structure(2, 2 if config.SCAR_CONNECTIVITY == 8 else 1)
    count = 0
    for month in range(1, 13):
        labels, found = ndimage.label(months == month, structure=links, output=np.int32)
        burned = labels > 0
        numbers[burned] = labels[burned] + count
        count += found
    return numbers
