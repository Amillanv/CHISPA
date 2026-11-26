"""The share of each layer cell that burned in one year, from MapBiomas Fogo through Earth Engine.

Ground that burned a short time before has little fuel. The growth risk examines the burned
ground of the years before an alert as an input. The map is the map of the burn scars, the
ground truth of the evaluation: thus an alert gets only the maps of the years before its year.
"""

from pathlib import Path

import ee
import numpy as np

from chispa import config
from chispa.earthengine import read_grid
from chispa.grid import layer_grid


def download_year(year: int, project: str, raw_dir: Path) -> list[Path]:
    """Save the burned share of each layer cell for one year, in percent, and return the path."""
    path = raw_dir / "burned" / f"{year}.npz"
    if not path.exists():
        ee.Initialize(project=project)
        # A pixel with no burn has no value in the map: it must count as 0 in the mean of a cell.
        burned = ee.Image(config.SCAR_ASSET).select(f"burned_monthly_{year}").gt(0).unmask(0)
        share = burned.reduceResolution(ee.Reducer.mean(), maxPixels=256).multiply(100)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, percent=read_grid(share.round().toUint8(), layer_grid()))
    return [path]


def read_year(year: int, raw_dir: Path) -> np.ndarray:
    """Return the burned share of each cell of the layer grid for one year, from 0 to 1."""
    path = raw_dir / "burned" / f"{year}.npz"
    if not path.exists():
        raise RuntimeError(f"Run `chispa fetch burned --year {year}` first.")
    return np.load(path)["percent"].astype(np.float32) / 100
