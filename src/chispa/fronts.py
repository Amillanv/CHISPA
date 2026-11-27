"""Fronts: the groups of VIIRS pixels of one look, and where each group went by the later looks.

An event can hold many fires, thus one direction for an event has little meaning. A front needs
no event: it is the pixels of one look that are adjacent. The later looks give the answer for a
front: new ground or not, how many new pixels, and in which sector of the compass.
A forecast learns from this answer, and the same answer scores a forecast.
`docs/method.md` section 11.26 gives the rules.
"""

from dataclasses import dataclass

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from chispa import config

SENSOR_FAMILY = "viirs"  # A GOES pixel is too large to show the side of a fire.


@dataclass(frozen=True)
class Look:
    """The pixels of one look with the front of each pixel, and the pixels that we knew before it.

    `older` holds only the known pixels near the look. None: no pixel is near.
    """

    points: np.ndarray
    labels: np.ndarray
    tree: cKDTree
    older: cKDTree | None


def metres(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Return positions as (metres north, metres east) on a flat map of the Pantanal box."""
    _, south, _, north = config.PANTANAL_BOX
    east_m = 111_320 * np.cos(np.deg2rad((south + north) / 2))
    return np.column_stack([np.asarray(lat) * 110_574, np.asarray(lon) * east_m])


def degrees(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return the latitude and the longitude of positions on the flat map of `metres`."""
    north_m, east_m = metres(np.array([1.0]), np.array([1.0]))[0]
    return points[..., 0] / north_m, points[..., 1] / east_m


def looks(observed: np.ndarray) -> np.ndarray:
    """Return the look number of each detection, in time sequence from 0.

    A look is the detections with no gap in time longer than the look gap in `config.py`.
    """
    order = np.argsort(observed, kind="stable")
    gap_s = config.LOOK_GAP.total_seconds()
    numbers = np.empty(len(observed), dtype=int)
    numbers[order] = np.cumsum(np.concatenate([[False], np.diff(observed[order]) > gap_s]))
    return numbers


def fronts(points: np.ndarray) -> np.ndarray:
    """Return the front number of each pixel of one look, from 0.

    Two pixels are in one front if a chain of pixels links them, with no step longer than the
    link distance in `config.py`.
    """
    count = len(points)
    pairs = cKDTree(points).query_pairs(config.FRONT_LINK_M, output_type="ndarray")
    graph = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(count, count))
    return connected_components(graph, directed=False)[1]


def make_look(points: np.ndarray, before: np.ndarray) -> Look:
    """Return the look of the pixels `points`. `before` holds each pixel that we knew before it."""
    margin = max(config.FRONT_REACH_M.values()) + config.GROWTH_FLOOR_M
    near = (before >= points.min(axis=0) - margin) & (before <= points.max(axis=0) + margin)
    older = before[near.all(axis=1)]
    return Look(points, fronts(points), cKDTree(points), cKDTree(older) if len(older) else None)


def sector(lines: np.ndarray) -> np.ndarray:
    """Return the sector of each line (metres north, metres east).

    Sector 0 has north at its centre. The numbers go clockwise.
    """
    width = 360 / config.FRONT_SECTORS
    degrees = np.degrees(np.arctan2(lines[:, 1], lines[:, 0])) % 360
    return ((degrees + width / 2) // width).astype(int) % config.FRONT_SECTORS


def answers(look: Look, later: np.ndarray, reach_m: float) -> dict[str, np.ndarray]:
    """Return what the later pixels say for each front of a look.

    A later pixel is a pixel of the front "again" if it is not farther than the floor from a
    pixel of the front. It is a new pixel if it is farther than the floor from each pixel of
    the look and from each older pixel, and not farther than the reach from a pixel of the look.
    A new pixel belongs to the front of the nearest pixel. Its line starts at that pixel.
    """
    count, floor = look.labels.max() + 1, config.GROWTH_FLOOR_M
    distance, near = look.tree.query(later, distance_upper_bound=reach_m)
    in_reach = np.isfinite(distance)
    again = np.bincount(look.labels[near[in_reach & (distance <= floor)]], minlength=count)
    new = np.nonzero(in_reach & (distance > floor))[0]
    if look.older is not None and len(new):
        new = new[look.older.query(later[new])[0] > floor]
    owner, lines = look.labels[near[new]], later[new] - look.points[near[new]]
    sectors = np.bincount(
        owner * config.FRONT_SECTORS + sector(lines), minlength=count * config.FRONT_SECTORS
    ).reshape(count, config.FRONT_SECTORS)
    found = {"again": again, "new": sectors.sum(axis=1), "sectors": sectors}
    return found | mean_lines(owner, lines, count)


def mean_lines(owner: np.ndarray, lines: np.ndarray, count: int) -> dict[str, np.ndarray]:
    """Return, for each front, the direction of the mean of its lines in degrees from north,
    and a high percentile of their lengths in metres. A front with no line has NaN."""
    lengths = np.hypot(lines[:, 0], lines[:, 1])
    north = np.bincount(owner, lines[:, 0], minlength=count)
    east = np.bincount(owner, lines[:, 1], minlength=count)
    has = np.bincount(owner, minlength=count) > 0
    distance = np.full(count, np.nan)
    for front in np.unique(owner):
        distance[front] = np.percentile(lengths[owner == front], config.GROWTH_ADVANCE_PERCENT)
    direction = np.where(has, np.degrees(np.arctan2(east, north)) % 360, np.nan)
    return {"direction_deg": direction, "distance_m": distance}
