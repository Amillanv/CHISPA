"""Build the store from the raw files.

The store is a result, not a source. This module makes it again from the raw folder.
Thus a change in a parser, or a new raw file, needs only a new build.
"""

import sqlite3
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import numpy as np

from chispa import config, fires, live
from chispa.grid import pantanal_grid
from chispa.models import Detection
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
    for year in config.YEAR_ROLES:
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
    logs = raw_dir / "live"
    for path in sorted((logs / "firms").glob("*/*.csv")):
        if path.stem >= first_day:
            detections, rejected = firms.parse_file(path, path.parent.name)
            yield "firms", after_stop(detections, raw_dir), rejected
    for path in sorted((logs / "goes").glob("*.csv")):
        if path.stem >= first_day:
            yield "noaa", goes.parse_file(path, "GOES19"), 0
    for path in sorted((logs / "inpe").glob("*.csv")):
        if path.stem >= first_day:
            detections, rejected, _ = inpe.parse_file(path)
            yield "inpe", detections, rejected


def after_stop(detections: list[Detection], raw_dir: Path) -> list[Detection]:
    """Give an estimate to each live FIRMS detection that a pass first saw after a stop.

    FIRMS gives no publication time. After a stop of the poller, the time of the first view is
    the time of our stop. The estimate is the observation time plus the delay in `config.py`.
    It is not before the newest pass before that read FIRMS, and not after the first view.
    """
    answered: dict[datetime, datetime] = {}
    found = []
    for detection in detections:
        seen = detection.available_at
        if seen not in answered:
            answered[seen] = live.answered_before(raw_dir, seen, "firms")
        if seen - answered[seen] > config.LIVE_POLL_LATE:
            guess = detection.observed_at + config.AVAILABLE_DELAY[detection.sensor_family]
            time = min(max(guess, answered[seen]), seen)
            detection = replace(detection, available_at=time, available_estimated=True)
        found.append(detection)
    return found


def add_live(raw_dir: Path, store: sqlite3.Connection, now: datetime) -> int:
    """Add the detections of the newest logs to the store. Return the number of new detections.

    The store ignores a detection that it holds. Thus a pass can read the same log again,
    and `build` gives the same detections from the same logs.
    """
    first_day = (now - config.LIVE_COMPLETE_AFTER).date().isoformat()
    return sum(add_detections(store, found) for _, found, _ in read_live(raw_dir, first_day))
