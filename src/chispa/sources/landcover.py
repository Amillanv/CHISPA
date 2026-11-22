"""MapBiomas land cover through Google Earth Engine.

The land cover says what a fire burns: forest, grassland, pasture and others.
The map has one class for each pixel of 30 m and each year. We save the most frequent class
of each cell of the layer grid: a VIIRS detection is not more exact than that.
"""

from pathlib import Path

import ee
import numpy as np

from chispa.earthengine import read_grid
from chispa.grid import Grid

ASSET = (
    "projects/mapbiomas-public/assets/brazil/lulc/collection10/"
    "mapbiomas_brazil_collection10_integration_v2"
)


def download_year(year: int, project: str, raw_dir: Path, grid: Grid) -> list[Path]:
    """Save the land cover of one year on the layer grid and return the path."""
    path = raw_dir / "landcover" / f"{year}.npz"
    if not path.exists():
        ee.Initialize(project=project)
        band = ee.Image(ASSET).select(f"classification_{year}")
        most = band.reduceResolution(ee.Reducer.mode(), maxPixels=256).unmask(0).toUint8()
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, cover=read_grid(most, grid))
    return [path]


def read_year(year: int, raw_dir: Path) -> np.ndarray:
    """Return the land cover class of each cell of the layer grid. 0 is "no class"."""
    path = raw_dir / "landcover" / f"{year}.npz"
    if not path.exists():
        raise RuntimeError(f"Run `chispa fetch landcover --year {year}` first.")
    return np.load(path)["cover"]
