"""The answers of the fronts against the flames in Sentinel-2 images.

The answer of a front comes from VIIRS only. Sentinel-2 gives a second view: flames are bright in
its short-wave band, with pixels of 20 m, near 14 UTC. This module finds the image in the window
of each front, gives the hot pixels of the image the rule of a new pixel, and compares the two
answers. `docs/method.md` section 11.27 gives the rules and the hypothesis.
"""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path

import numpy as np

from chispa import config, fronts
from chispa.earthengine import Box, again
from chispa.evaluation import burn
from chispa.evaluation import fronts as steps
from chispa.evaluation.advance import turn
from chispa.evaluation.report import percentile, share
from chispa.grid import pantanal_grid
from chispa.sources import border, sentinel2


def box_of(lat: np.ndarray, lon: np.ndarray, reach_m: float) -> Box:
    """Return the box of the pixels of a front with the reach around it: S, W, N, E."""
    north_m, east_m = fronts.metres(np.array([1.0]), np.array([1.0]))[0]  # One degree in metres.
    d_lat, d_lon = reach_m / north_m, reach_m / east_m
    return (lat.min() - d_lat, lon.min() - d_lon, lat.max() + d_lat, lon.max() + d_lon)


def _number(value: float) -> float | str:
    return "" if np.isnan(value) else round(float(value), 1)


def check_front(look: fronts.Look, front: int, place: dict, answers: dict) -> dict | None:
    """Return the row of one front: its image, its answer and the flames. None: no image.

    `place` has the start of the look and the positions of its pixels. `answers` has the rows of
    the look. The image is the first in the window of 12 hours, or in the window of 24 hours.
    """
    member = look.labels == front
    lat, lon = place["lat"][member], place["lon"][member]
    start = datetime.fromtimestamp(place["start"], UTC)
    for hours, (low, high) in config.FRONT_WINDOWS_H.items():
        box = box_of(lat, lon, config.FRONT_REACH_M[hours])
        times = (start + timedelta(hours=low), start + timedelta(hours=high))
        views = again(lambda box=box, times=times: sentinel2.cloud_free_views(box, *times))
        if views:
            break
    else:
        return None
    name, at, clear = views[0]
    hot = fronts.metres(*sentinel2.hot_pixels(name, box))
    flames = fronts.answers(look, hot, config.FRONT_REACH_M[hours])
    return {
        "start": int(place["start"]),
        "lat": round(float(lat.mean()), 5),
        "lon": round(float(lon.mean()), 5),
        "pixels": int(member.sum()),
        "hours": hours,
        "image": name,
        "image_hours": round((at.timestamp() - place["start"]) / 3600, 2),
        "clear_share": round(float(clear or 0.0), 4),
        "answer": steps.ANSWERS[answers[f"answer_{hours}"][front]],
        "direction_deg": _number(answers[f"direction_deg_{hours}"][front]),
        "distance_m": _number(answers[f"distance_m_{hours}"][front]),
        "new_hot_pixels": int(flames["new"][front]),
        "flames_direction_deg": _number(flames["direction_deg"][front]),
        "flames_distance_m": _number(flames["distance_m"][front]),
    }


def measure(year: int, store_path: Path, raw_dir: Path, path: Path) -> None:
    """Find the image of each front of one year, and save one row for each front with an image."""
    pixels = steps.load_pixels(sqlite3.connect(store_path), year)
    masks = steps.open_masks(raw_dir, year)
    rings = border.read_rings(raw_dir / "border" / "pantanal.geojson")
    in_biome, rows = border.rasterize(rings, pantanal_grid()), []
    with ThreadPoolExecutor(max_workers=8) as workers:
        for a, b, look in steps.each_look(pixels):
            answers = steps.look_rows(pixels, (a, b), look, masks)
            place = {"start": pixels["seconds"][a], "lat": pixels["lat"][a:b]}
            place["lon"] = pixels["lon"][a:b]
            chosen = np.nonzero(steps.kept(answers, in_biome))[0]
            check = partial(check_front, look, place=place, answers=answers)
            rows += [row for row in workers.map(check, chosen) if row is not None]
    burn.write(path, rows)


def table(rows: list[dict]) -> list[dict]:
    """Return the answers of the fronts against the flames, for each window.

    Flames on new ground: the minimum number of new hot pixels or more. No flames on new ground:
    no new hot pixel, in a box with the minimum clear share.
    """
    out = []
    for hours in config.FRONT_WINDOWS_H:
        part = [row for row in rows if int(row["hours"]) == hours]
        flames = [row for row in part if int(row["new_hot_pixels"]) >= config.FLAMES_MIN_HOT]
        clear = [row for row in part if float(row["clear_share"]) >= config.FLAMES_MIN_CLEAR]
        none = [row for row in clear if int(row["new_hot_pixels"]) == 0]
        new = [sum(row["answer"] == steps.ANSWERS[0] for row in group) for group in (flames, none)]
        both = [row for row in flames if row["answer"] == steps.ANSWERS[0]]
        turns = [
            turn(float(row["direction_deg"]), float(row["flames_direction_deg"])) for row in both
        ]
        near = sum(angle <= config.ADVANCE_SAME_DEG for angle in turns)
        out.append(
            {
                "hours": hours,
                "fronts_with_image": len(part),
                "flames_on_new_ground": len(flames),
                "of_them_new_ground": new[0],
                "share_of_them": share(new[0], len(flames)),
                "of_them_not_visible": sum(row["answer"] == steps.ANSWERS[-1] for row in flames),
                "no_flames_on_new_ground": len(none),
                "of_those_new_ground": new[1],
                "share_of_those": share(new[1], len(none)),
                "directions_in_45": near,
                "directions_compared": len(both),
                "distance_m_median": percentile([float(row["distance_m"]) for row in both], 50),
                "flames_distance_m_median": percentile(
                    [float(row["flames_distance_m"]) for row in both], 50
                ),
            }
        )
    return out
