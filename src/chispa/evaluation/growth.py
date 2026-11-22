"""Measured growth against what we can check.

For each event, the advance and the speed between two VIIRS passes. No source gives the
position of a fire front. Thus the table compares short and long times between passes:
a short time shows the error of the positions.
"""

import sqlite3
from pathlib import Path

import numpy as np

from chispa import config, growth
from chispa.evaluation.report import percentile, share
from chispa.grid import pantanal_grid
from chispa.sources import border, passes

STEP_QUERY = """
SELECT m.event_id, d.platform, CAST(strftime('%s', d.observed_at) AS INTEGER), d.lat, d.lon
FROM detections d JOIN memberships m ON m.detection_id = d.id
WHERE d.sensor_family = ? AND m.event_id >= ? AND m.event_id < ?
ORDER BY m.event_id
"""
SAME_PASS_S = 600  # A granule this near to a pass with detections is a part of that pass.


def load_events(store: sqlite3.Connection, year: int, raw_dir: Path) -> dict[int, tuple]:
    """Return the VIIRS detections in the biome for each event of one fused year:
    event -> (platform, observed time in seconds, latitude, longitude)."""
    first_id = year * 10_000_000
    rows = store.execute(STEP_QUERY, (growth.SENSOR_FAMILY, first_id, first_id + 10_000_000))
    event, platform, observed, lat, lon = (np.array(column) for column in zip(*rows, strict=True))
    grid = pantanal_grid()
    in_biome = border.rasterize(border.read_rings(raw_dir / "border" / "pantanal.geojson"), grid)
    keep = in_biome[grid.rows_cols(lat, lon)]
    del in_biome
    fields = (platform[keep], observed[keep].astype(float), lat[keep], lon[keep])
    starts = np.nonzero(np.concatenate([[True], np.diff(event[keep]) != 0]))[0]
    ends = [*starts[1:], keep.sum()]
    return {
        int(event[keep][start]): tuple(field[start:end] for field in fields)
        for start, end in zip(starts, ends, strict=True)
    }


def has_empty_pass(step: dict, lat: float, lon: float, granules: list, starts: np.ndarray) -> bool:
    """Return True if a VIIRS satellite passed over the position between the two passes of a step,
    with no detection of the event."""
    before = step["at"] - step["hours"] * 3600
    first = np.searchsorted(starts, before + SAME_PASS_S)
    last = np.searchsorted(starts, step["at"] - SAME_PASS_S)
    return any(passes.covers(granules[number][2], lat, lon) for number in range(first, last))


def event_steps(events: dict[int, tuple], granules: list) -> list[dict]:
    """Return the steps of all events, each with the mark of an empty pass."""
    starts = np.array([start for _, start, _ in granules])
    rows = []
    for platform, observed, lat, lon in events.values():
        numbers = growth.passes(platform, observed)
        for step in growth.steps(lat, lon, numbers, observed):
            step["empty_pass"] = has_empty_pass(step, lat.mean(), lon.mean(), granules, starts)
            rows.append(step)
    return rows


def step_table(steps: list[dict]) -> list[dict]:
    """Return the advance and the speed of the steps, by the time between the two passes.

    The speed is for the steps that have one: a new pixel, and not a short time between the passes.
    """
    hours = np.array([step["hours"] for step in steps])
    advance = np.array([step["advance_m"] for step in steps])
    moved = np.array([step["new_pixels"] > 0 for step in steps])
    speeds = np.array([step["speed_m_h"] or np.nan for step in steps])
    empty = np.array([step["empty_pass"] for step in steps])
    limits = config.GROWTH_HOUR_CLASSES
    classes = [
        (f"{low:g} to {high:g}", (hours >= low) & (hours < high))
        for low, high in zip(limits[:-1], limits[1:], strict=True)
    ]
    rows = []
    for label, part in (*classes, ("all", np.ones(len(steps), dtype=bool))):
        speed = speeds[part & ~np.isnan(speeds)]
        rows.append(
            {
                "hours_between_passes": label,
                "steps": int(part.sum()),
                "advance_m_median": percentile(advance[part], 50),
                "advance_m_p90": percentile(advance[part], 90),
                "floor_m": config.GROWTH_FLOOR_M,
                "steps_with_new_pixels": int((part & moved).sum()),
                "new_pixel_share": share((part & moved).sum(), part.sum()),
                "speed_m_h_median": percentile(speed, 50),
                "speed_m_h_p90": percentile(speed, 90),
                "steps_after_empty_pass": int((part & empty).sum()),
            }
        )
    return rows


def step_rows(year: int, store_path: Path, raw_dir: Path) -> list[dict]:
    """Return the table `growth_steps` of one fused year."""
    store = sqlite3.connect(store_path)
    steps = event_steps(load_events(store, year, raw_dir), passes.read_year(year, raw_dir))
    return step_table(steps)
