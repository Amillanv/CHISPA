"""Visibility: could GOES examine the place of a fire while it burned?

A fire with no detection has two possible causes. The sensors could not see the place,
or they saw it and found no fire: the fire was too small or too cool for them.
The GOES mask gives a class for each pixel in each scan. We read the class of the pixel
that holds most of a fire, for one scan of each hour, in the days when the fire burned.
"""

from pathlib import Path

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

from chispa.evaluation.match import Fields, first_times, near_in_time
from chispa.evaluation.report import percentile
from chispa.evaluation.run import prepare
from chispa.grid import Grid, pantanal_grid
from chispa.sources import goes

EXAMINED = ("no_fire", "fire", "possible_fire")
MAX_POINTS = 2000  # We find the pixel of a large fire from this many of its points.


def main_pixels(numbers: np.ndarray, grid: Grid, wanted: np.ndarray, mask_grid: Fields) -> dict:
    """Return, for each wanted fire, the (row, column) of the GOES pixel that holds most of it."""
    scale = np.cos(np.deg2rad(mask_grid["lat"].mean()))
    flat = np.column_stack([mask_grid["lat"].ravel(), mask_grid["lon"].ravel() * scale])
    tree = cKDTree(flat)
    places = ndimage.find_objects(numbers)
    lats, lons = grid.lats(), grid.lons()
    pixels = {}
    for fire in wanted.tolist():
        rows, cols = np.nonzero(numbers[places[fire - 1]] == fire)
        step = max(len(rows) // MAX_POINTS, 1)
        lat = lats[rows[::step] + places[fire - 1][0].start]
        lon = lons[cols[::step] + places[fire - 1][1].start]
        _, nearest = tree.query(np.column_stack([lat, lon * scale]))
        most = np.bincount(nearest).argmax()
        pixels[fire] = divmod(int(most), mask_grid["lat"].shape[1])
    return pixels


def read_series(folder: Path, pixels: dict) -> tuple[np.ndarray, np.ndarray]:
    """Return the scan times of one year, and the mask class of each pixel in each scan.

    The classes have one row for each scan and one column for each fire, in the dict sequence.
    """
    rows = np.array([row for row, _ in pixels.values()])
    cols = np.array([col for _, col in pixels.values()])
    times, classes = [], []
    for path in sorted(folder.glob("????-??-??.npz")):
        day = np.load(path)
        if len(day["times"]):
            times.append(day["times"].astype("datetime64[s]"))
            classes.append(day["mask"][:, rows, cols])
    return np.concatenate(times), np.concatenate(classes)


def fire_rows(fires: Fields, wanted: np.ndarray, times: np.ndarray, classes: np.ndarray) -> Fields:
    """Return, for each wanted fire, the counts of its scans by what GOES could see.

    A scan counts for a fire if the fire burned near its time, by the time rule of the match.
    """
    month = times.astype("datetime64[M]").astype(int) % 12 + 1
    day = (times.astype("datetime64[D]") - times.astype("datetime64[Y]")).astype(int) + 1
    groups = goes.mask_groups(classes)
    counts = {name: [] for name in ("scans", "examined", "cloud", "possible_fire")}
    for column, fire in enumerate(wanted.tolist()):
        seen = groups[near_in_time(fires, np.array([fire]), month, day), column]
        counts["scans"].append(len(seen))
        counts["examined"].append(int(np.isin(seen, EXAMINED).sum()))
        counts["cloud"].append(int((seen == "cloud").sum()))
        counts["possible_fire"].append(int((seen == "possible_fire").sum()))
    return {name: np.array(values) for name, values in counts.items()}


def table(counts: Fields, parts: dict[str, np.ndarray]) -> list[dict]:
    """Return one row for each part of the fires: how frequently GOES examined their place.

    A share is for one fire: its scans of one kind, divided by all its scans. A fire with no
    scan is not in the shares. The table gives the median share of the fires of the part.
    """
    rows = []
    for name, part in parts.items():
        scans, examined = counts["scans"][part], counts["examined"][part]
        has = scans > 0
        share_examined = examined[has] / scans[has]
        rows.append(
            {
                "fires": name,
                "count": int(part.sum()),
                "with_scans": int(has.sum()),
                "scans_median": percentile(scans[has], 50),
                "examined_share_median": percentile(share_examined, 50),
                "cloud_share_median": percentile(counts["cloud"][part][has] / scans[has], 50),
                "examined_under_half": int((share_examined < 0.5).sum()),
                "never_examined": int((examined[has] == 0).sum()),
                "with_possible_fire": int((counts["possible_fire"][part] > 0).sum()),
            }
        )
    return rows


def visibility(year: int, store_path: Path, raw_dir: Path) -> list[dict]:
    """Return the visibility table of the counted fires of one fused year."""
    detections, pairs, fires, _ = prepare(year, store_path, raw_dir)
    count = len(fires["area_ha"]) - 1
    everything = np.ones(len(detections["family"]), dtype=bool)
    found = np.isfinite(first_times(pairs, everything, detections["observed"], count))
    by_goes = np.isfinite(
        first_times(pairs, detections["family"] == "abi", detections["observed"], count)
    )
    wanted = np.nonzero(fires["counted"])[0]
    folder = raw_dir / "goes_mask"
    mask_grid = dict(np.load(folder / "grid.npz"))
    numbers = np.load(store_path.parent / "fires" / f"{year}.npz")["numbers"]
    pixels = main_pixels(numbers, pantanal_grid(), wanted, mask_grid)
    times, classes = read_series(folder / str(year), pixels)
    parts = {
        "counted fires with no detection": ~found[wanted],
        "counted fires with a detection, not from GOES": found[wanted] & ~by_goes[wanted],
        "counted fires with a GOES detection": by_goes[wanted],
    }
    return table(fire_rows(fires, wanted, times, classes), parts)
