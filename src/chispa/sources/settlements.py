"""The number of people on the ground, from the Global Human Settlement Layer (GHSL).

A fire near many people has a larger effect. The layer estimates the people in each cell
of 100 m for the year 2020. We save the people in each cell of the layer grid.
"""

from pathlib import Path

import ee
import numpy as np

from chispa.earthengine import read_grid
from chispa.grid import Grid

ASSET = "JRC/GHSL/P2023A/GHS_POP/2020"
SOURCE_CELL_M2 = 10_000  # One cell of the layer is 100 m by 100 m, in an equal-area projection.


def download(project: str, raw_dir: Path, grid: Grid) -> list[Path]:
    """Save the number of people in each cell of the layer grid and return the path."""
    path = raw_dir / "settlements" / "people_2020.npz"
    if not path.exists():
        ee.Initialize(project=project)
        # A sum of source cells counts a cell at an edge two times. Thus we use the mean number
        # of people for each square metre, then the area of our cell.
        source = ee.Image(ASSET)
        # The layer has a negative value for "no data". That is no people, not a number of people.
        density = source.max(0).reduceResolution(ee.Reducer.mean(), maxPixels=64)
        people = density.multiply(ee.Image.pixelArea()).divide(SOURCE_CELL_M2).unmask(0).toFloat()
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, people=read_grid(people, grid))
    return [path]


def read(raw_dir: Path) -> np.ndarray:
    """Return the number of people in each cell of the layer grid."""
    path = raw_dir / "settlements" / "people_2020.npz"
    if not path.exists():
        raise RuntimeError("Run `chispa fetch settlements` first.")
    return np.load(path)["people"]
