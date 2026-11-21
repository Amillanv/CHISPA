"""Build the store from the raw files.

The store is a result, not a source. This module makes it again from the raw folder.
Thus a change in a parser, or a new raw file, needs only a new build.
"""

from pathlib import Path

import numpy as np

from chispa import config, fires
from chispa.grid import pantanal_grid
from chispa.sources import border, burnday, firms, goes, inpe, scars
from chispa.store import add_detections, add_fires, open_store


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
        scar_count, fire_count = build_fires(year, raw_dir, store_path.parent, store)
        totals[f"scars {year}"] = [1, scar_count, 0]
        totals[f"fires {year}"] = [1, fire_count, 0]
    store.close()
    new_path.replace(store_path)
    return totals


def build_fires(year: int, raw_dir: Path, data_dir: Path, store) -> tuple[int, int]:
    """Find the fires of one year in the biome. Save them, and save the fire grid.

    The fire grid is a file, not a table: it has one number for each 30 m pixel.
    Return the number of scars and the number of fires.
    """
    grid = pantanal_grid()
    in_biome = border.rasterize(border.read_rings(raw_dir / "border" / "pantanal.geojson"), grid)
    months = scars.read_year(year, raw_dir, grid) * in_biome
    scar_numbers = scars.find_scars(months)
    found, numbers = fires.find_fires(
        months, scar_numbers, grid, burnday.read_year(year, raw_dir), burnday.burnday_grid()
    )
    add_fires(store, year, found)
    path = data_dir / "fires" / f"{year}.npz"
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, numbers=numbers)
    return int(scar_numbers.max()), len(found)


def read_raw(raw_dir: Path):
    """Give (source, detections, rejected rows) for each raw file, in a fixed sequence."""
    for path in sorted((raw_dir / "firms").glob("*/*.csv")):
        detections, rejected = firms.parse_file(path, path.parent.name)
        yield "firms", detections, rejected
    for path in sorted((raw_dir / "goes").glob("*.csv")):
        yield "noaa", goes.parse_file(path, "GOES16"), 0
    for path in sorted((raw_dir / "inpe").glob("focos_mensal_br_*")):
        if path.suffix in (".csv", ".zip"):
            detections, rejected, _ = inpe.parse_file(path)
            yield "inpe", detections, rejected
    yield from read_live(raw_dir, first_day="")


def read_live(raw_dir: Path, first_day: str):
    """Give (source, detections, rejected rows) for each log of the live poller.

    `first_day` is a date as text. A log of an earlier day is not read.
    """
    live = raw_dir / "live"
    for path in sorted((live / "firms").glob("*/*.csv")):
        if path.stem >= first_day:
            detections, rejected = firms.parse_file(path, path.parent.name)
            yield "firms", detections, rejected
    for path in sorted((live / "goes").glob("*.csv")):
        if path.stem >= first_day:
            yield "noaa", goes.parse_file(path, "GOES19"), 0
    for path in sorted((live / "inpe").glob("*.csv")):
        if path.stem >= first_day:
            detections, rejected, _ = inpe.parse_file(path)
            yield "inpe", detections, rejected
