"""Build the store from the raw files.

The store is a result, not a source. This module makes it again from the raw folder.
Thus a change in a parser, or a new raw file, needs only a new build.
"""

import sqlite3
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import numpy as np

from chispa import config, fires, polls
from chispa.grid import pantanal_grid
from chispa.models import Detection
from chispa.sources import border, burnday, firms, goes, inpe, scars
from chispa.store import (
    add_detections,
    add_fires,
    mark_stale,
    open_store,
    read_log_sizes,
    save_log_size,
)


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
    # The annual file of an older year, then the monthly files of the newer years.
    for path in sorted((raw_dir / "inpe").glob("focos_*")):
        if path.suffix in (".csv", ".zip"):
            detections, rejected, _ = inpe.parse_file(path)
            yield "inpe", detections, rejected
    yield from read_live(raw_dir)


def read_live(raw_dir: Path):
    """Give (source, detections, rejected rows) for each log of the live poller."""
    for source, path in live_logs(raw_dir):
        yield source, *read_log(source, path, raw_dir)


def live_logs(raw_dir: Path) -> list[tuple[str, Path]]:
    """Return (source, path) for each log of the live poller, in a fixed sequence."""
    logs = raw_dir / "live"
    return (
        [("firms", path) for path in sorted((logs / "firms").glob("*/*.csv"))]
        + [("noaa", path) for path in sorted((logs / "goes").glob("*.csv"))]
        + [("inpe", path) for path in sorted((logs / "inpe").glob("*.csv"))]
    )


def read_log(source: str, path: Path, raw_dir: Path) -> tuple[list[Detection], int]:
    """Return the detections of one live log and the number of rejected rows."""
    if source == "firms":
        detections, rejected = firms.parse_file(path, path.parent.name)
        return after_stop(detections, raw_dir, path.parent.name), rejected
    if source == "noaa":
        return goes.parse_file(path, "GOES19"), 0
    detections, rejected, _ = inpe.parse_file(path)
    return detections, rejected


def after_stop(detections: list[Detection], raw_dir: Path, product: str) -> list[Detection]:
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
            answered[seen] = polls.answered_before(raw_dir, seen, "firms", product)
        if seen - answered[seen] > config.LIVE_POLL_LATE:
            guess = detection.observed_at + config.AVAILABLE_DELAY[detection.sensor_family]
            time = min(max(guess, answered[seen]), seen)
            detection = replace(detection, available_at=time, available_estimated=True)
        found.append(detection)
    return found


def add_live(raw_dir: Path, store: sqlite3.Connection) -> tuple[int, int]:
    """Add the detections of each live log that changed to the store. Return the number of new
    detections and the number of rejected rows.

    The store has the size of each log that it read. A log only grows: a log with a different
    size has new rows. Thus a computer that was off for some days reads each log that it did not
    read, and not only the logs of the newest days. The store ignores a detection that it holds.
    Before the detections of a log go in, their years get a mark (`store.mark_stale`). The mark
    stays to the end of the next fusion of the year: an update that stops in the middle loses
    no fusion.
    """
    read, new, rejected = read_log_sizes(store), 0, 0
    poll_logs = (raw_dir / "live" / "polls").glob("*.csv")
    newest_poll = max((path.stat().st_mtime for path in poll_logs), default=0.0)
    for source, path in live_logs(raw_dir):
        name, facts = path.relative_to(raw_dir).as_posix(), path.stat()
        # The estimate of a FIRMS row needs the poll log of its pass. A pass writes the poll row
        # of a product directly after the rows of that product, and `rsync` takes the times of
        # all files before it copies one. Thus a FIRMS log that is newer than the poll log came
        # in a copy that is not complete: it waits for the next update.
        waits = source == "firms" and facts.st_mtime > newest_poll
        if read.get(name) == facts.st_size or waits:
            continue
        detections, bad = read_log(source, path, raw_dir)
        mark_stale(store, {detection.available_at.year for detection in detections})
        new += add_detections(store, detections)
        rejected += bad
        save_log_size(store, name, facts.st_size)
    return new, rejected
