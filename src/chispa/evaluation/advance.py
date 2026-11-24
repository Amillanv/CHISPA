"""The advance of VIIRS against the new burned ground between two Sentinel-2 images.

`growth.py` gives how far an event moved, from its VIIRS pixels. That measure had no reference.
For a long event with two clear images in its days, this module measures the same advance two
times: from the VIIRS pixels, and from the new burned ground of the second image.
`docs/method.md` section 11.20 gives the rules.
"""

import csv
import hashlib
import sqlite3
import statistics
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path

import numpy as np

from chispa import config, earthengine, growth
from chispa.evaluation import burn, curve
from chispa.evaluation.report import share
from chispa.grid import layer_grid
from chispa.sources import border, sentinel2, sentinel2_ground

FIELDS = ["id", "settings", "view_a", "view_b", "viirs_advance_m", "viirs_direction_deg"]
FIELDS += ["ground_advance_m", "ground_direction_deg", "old_ha", "new_ha"]
EVENTS = """
SELECT id, lat, lon, south, west, north, east, first_observed_at, last_observed_at FROM events
WHERE id >= ? AND id < ? AND level = 'HIGH' AND families LIKE '%viirs%'
  AND julianday(last_observed_at) - julianday(first_observed_at) >= ? ORDER BY id
"""
PIXELS = """
SELECT m.event_id, CAST(strftime('%s', d.observed_at) AS INTEGER), d.lat, d.lon
FROM detections d JOIN memberships m ON m.detection_id = d.id
WHERE d.sensor_family = ? AND m.event_id >= ? AND m.event_id < ?
"""


def signature() -> str:
    """Return a short mark of each value that changes a measure of this module."""
    days = (config.ADVANCE_MIN_DAYS, config.ADVANCE_VIEW_DAYS, config.IMAGE_MIN_CLEAR)
    floor = (config.GROWTH_FLOOR_M, config.GROWTH_ADVANCE_PERCENT)
    return hashlib.sha256(repr((curve.signature(), days, floor)).encode()).hexdigest()[:8]


def long_events(year: int, store_path: Path, raw_dir: Path) -> tuple[list[dict], dict]:
    """Return the long HIGH events of a year in the biome, and the VIIRS pixels of each.

    The pixels of an event are three arrays: the time in seconds, the latitude and the longitude.
    """
    store = sqlite3.connect(store_path)
    store.row_factory = sqlite3.Row
    span = (year * 10_000_000, (year + 1) * 10_000_000)
    grid = layer_grid()
    in_biome = border.rasterize(border.read_rings(raw_dir / "border" / "pantanal.geojson"), grid)
    found = store.execute(EVENTS, (*span, config.ADVANCE_MIN_DAYS)).fetchall()
    targets = [dict(row) for row in found if in_biome[grid.rows_cols(row["lat"], row["lon"])]]
    wanted = {target["id"] for target in targets}
    pixels: dict[int, list] = {event: [] for event in wanted}
    for event, *pixel in store.execute(PIXELS, (growth.SENSOR_FAMILY, *span)):
        if event in wanted:
            pixels[event].append(pixel)
    return targets, {event: np.array(rows, dtype=float).T for event, rows in pixels.items()}


def choose(views: list[tuple], first: datetime, last: datetime) -> tuple | None:
    """Return the times of view A and of view B, or None.

    A view is (name, time, cloud-free share of the box). View A is the first clear view after
    the first detection. View B is the first clear view the minimum days after view A.
    """
    end = last + timedelta(days=config.BURN_DAYS)
    clear = [at for _, at, part in views if part >= config.IMAGE_MIN_CLEAR and first < at <= end]
    if not clear:
        return None
    later = [at for at in clear if at >= clear[0] + timedelta(days=config.ADVANCE_VIEW_DAYS)]
    return (clear[0], later[0]) if later else None


def viirs_step(pixels: np.ndarray, at_a: float, at_b: float) -> dict | None:
    """Return the advance of the VIIRS pixels from the time of view A to the time of view B.

    The older pixels are those to view A. With no pixel in one of the two groups: None.
    The advance is that of `growth.py`. The direction is from the centre of the older pixels to
    the centre of the new pixels: the same definition as for the burned ground.
    """
    times, lat, lon = pixels
    old, new = times <= at_a, (times > at_a) & (times <= at_b)
    if not old.any() or not new.any():
        return None
    chosen = old | new
    step = growth.steps(lat[chosen], lon[chosen], new[chosen].astype(int), times[chosen])
    centres = [(float(lat[group].mean()), float(lon[group].mean())) for group in (old, new)]
    return {"advance_m": step[0]["advance_m"], "direction_deg": bearing(*centres)}


def bearing(start: tuple, end: tuple) -> float:
    """Return the direction from one (lat, lon) to a second one, in degrees from north."""
    north_m = (end[0] - start[0]) * 110_574
    east_m = (end[1] - start[1]) * 111_320 * np.cos(np.deg2rad(start[0]))
    return round(float(np.degrees(np.arctan2(east_m, north_m)) % 360), 1)


def _measure(target: dict, pixels: np.ndarray) -> dict:
    """Return the two advances of one event. A value that we cannot measure is an empty text."""
    row = {"id": target["id"], "settings": signature()} | dict.fromkeys(FIELDS[2:], "")
    box = burn.with_margin(*(float(target[name]) for name in ("south", "west", "north", "east")))
    first = datetime.fromisoformat(target["first_observed_at"])
    last = datetime.fromisoformat(target["last_observed_at"])
    before, after = burn.periods(first, last)
    views = earthengine.again(partial(sentinel2.cloud_free_views, box, first, after[1]))
    times = choose(views, first, last)
    if times is None:
        return row
    row |= {"view_a": times[0].date().isoformat(), "view_b": times[1].date().isoformat()}
    step = viirs_step(pixels, *(at.timestamp() for at in times))
    request = partial(sentinel2_ground.new_ground, box, before, times, curve.rule()[0])
    ground = earthengine.again(request)
    if step is not None:
        row |= {"viirs_advance_m": round(step["advance_m"], 1)}
        row["viirs_direction_deg"] = step["direction_deg"]
    if ground is not None:
        row |= {"ground_advance_m": ground["advance_m"], "old_ha": ground["old_ha"]}
        row |= {"new_ha": ground["new_ha"]}
        row["ground_direction_deg"] = bearing(ground["old_place"], ground["new_place"])
    return row


def measure(targets: list[dict], pixels: dict, path: Path) -> None:
    """Measure each event that is not in the file, and append it to the file.

    A file with different columns, or with measures of different values, stops the run.
    """
    old = burn.read(path) if path.exists() else []
    if old and (list(old[0]) != FIELDS or {row["settings"] for row in old} != {signature()}):
        raise RuntimeError(f"{path} has measures of different settings. Delete it, then run again.")
    done = {row["id"] for row in old}
    open_targets = [target for target in targets if str(target["id"]) not in done]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="") as file, ThreadPoolExecutor(max_workers=8) as workers:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        if not done:
            writer.writeheader()
        jobs = workers.map(lambda target: _measure(target, pixels[target["id"]]), open_targets)
        for row in jobs:
            writer.writerow(row)
            file.flush()


def turn(first: float, second: float) -> float:
    """Return the angle between two directions, in degrees from 0 to 180."""
    angle = abs(first - second) % 360
    return min(angle, 360 - angle)


def table(rows: list[dict]) -> list[dict]:
    """Return one row: how many events have the two advances, and how well the two agree.

    The ratio is the advance of VIIRS divided by the advance of the burned ground.
    `config.py` has the limits of an agreement.
    """
    both = [row for row in rows if row["viirs_advance_m"] != "" and row["ground_advance_m"] != ""]
    pairs = [(float(row["viirs_advance_m"]), float(row["ground_advance_m"])) for row in both]
    ratios = [viirs / ground for viirs, ground in pairs if ground > 0]
    factor = config.ADVANCE_SAME_FACTOR
    near = sum(1 / factor <= ratio <= factor for ratio in ratios)
    turns = [
        turn(float(row["viirs_direction_deg"]), float(row["ground_direction_deg"]))
        for row in both
        if row["viirs_direction_deg"] != ""
    ]
    return [
        {
            "events": len(rows),
            "with_two_views": sum(row["view_b"] != "" for row in rows),
            "with_two_advances": len(ratios),
            "viirs_advance_m_median": round(statistics.median(p[0] for p in pairs))
            if pairs
            else None,
            "ground_advance_m_median": round(statistics.median(p[1] for p in pairs))
            if pairs
            else None,
            "ratio_median": round(statistics.median(ratios), 4) if ratios else None,
            "same_advance": near,
            "same_advance_share": share(near, len(ratios)),
            "with_two_directions": len(turns),
            "turn_deg_median": round(statistics.median(turns), 1) if turns else None,
            "same_direction": sum(angle <= config.ADVANCE_SAME_DEG for angle in turns),
            "same_direction_share": share(
                sum(angle <= config.ADVANCE_SAME_DEG for angle in turns), len(turns)
            ),
        }
    ]
