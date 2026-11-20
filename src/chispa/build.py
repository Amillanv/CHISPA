"""Build the store from the raw files.

The store is a result, not a source. This module makes it again from the raw folder.
Thus a change in a parser, or a new raw file, needs only a new build.
"""

from pathlib import Path

import numpy as np

from chispa import config
from chispa.grid import pantanal_grid
from chispa.sources import border, firms, goes, inpe, scars
from chispa.store import add_detections, add_scars, open_store


def build_store(raw_dir: Path, store_path: Path) -> dict[str, list[int]]:
    """Make a new store and return [files, detections, rejected rows] for each source.

    The new store replaces the old store only when the build is complete.
    """
    new_path = store_path.with_name(store_path.name + ".building")
    new_path.unlink(missing_ok=True)
    store = open_store(new_path)
    totals: dict[str, list[int]] = {}
    for source, detections, rejected in read_raw(raw_dir):
        total = totals.setdefault(source, [0, 0, 0])
        total[0] += 1
        total[1] += add_detections(store, detections)
        total[2] += rejected
    for year in (config.DEVELOPMENT_YEAR, config.TEST_YEAR):
        totals[f"scars {year}"] = [1, build_scars(year, raw_dir, store_path.parent, store), 0]
    store.close()
    new_path.replace(store_path)
    return totals


def build_scars(year: int, raw_dir: Path, data_dir: Path, store) -> int:
    """Find the burn scars of one year in the biome. Save them, and save the scar grid.

    The scar grid is a file, not a table: it has one number for each 30 m pixel.
    """
    grid = pantanal_grid()
    in_biome = border.rasterize(border.read_rings(raw_dir / "border" / "pantanal.geojson"), grid)
    months = scars.read_year(year, raw_dir, grid) * in_biome
    found, numbers = scars.find_scars(months, grid, year)
    add_scars(store, found)
    path = data_dir / "scars" / f"numbers_{year}.npz"
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, numbers=numbers)
    return len(found)


def read_raw(raw_dir: Path):
    """Give (source, detections, rejected rows) for each raw file, in a fixed sequence."""
    for path in sorted((raw_dir / "firms").glob("*/*.csv")):
        detections, rejected = firms.parse_file(path, path.parent.name)
        yield "firms", detections, rejected
    for path in sorted((raw_dir / "goes").glob("*.csv")):
        yield "noaa", goes.parse_file(path), 0
    for path in sorted((raw_dir / "inpe").glob("focos_mensal_br_*")):
        if path.suffix in (".csv", ".zip"):
            detections, rejected, _ = inpe.parse_file(path)
            yield "inpe", detections, rejected
