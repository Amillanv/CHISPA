"""Severity: one number for an event, and the facts that give it.

A brigade with few people must know which alert to go to first. The severity puts together
what the fire does (power, extent, advance), what it burns (land cover) and what is near it
(people, protected land, indigenous land). It is a sum of points with fixed rules, thus
a person can calculate it again from the facts. It is a heuristic, not a measure of damage.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import ndimage

from chispa import config
from chispa.grid import Grid, layer_grid
from chispa.sources import landcover, protected, settlements


@dataclass(frozen=True)
class Layers:
    """The ground layers on the layer grid: one value for each cell."""

    grid: Grid
    cover: np.ndarray  # The land cover class.
    people_near: np.ndarray  # The people in the square around the cell.
    distance_km: dict[str, np.ndarray]  # For each kind of land: the distance to the nearest area.
    nearest: dict[str, np.ndarray]  # For each kind of land: the identifier of that area.
    names: dict[int, str]


def load_layers(raw_dir: Path, cover_year: int) -> Layers:
    """Read the layers and make the values that the facts need."""
    grid = layer_grid()
    side = config.SEVERITY_PEOPLE_CELLS
    people = settlements.read(raw_dir).astype(float)
    # The filter gives a very small negative number where there are no people.
    people_near = np.clip(
        ndimage.uniform_filter(people, size=side, mode="constant") * side**2, 0, None
    )
    cell_km = (
        grid.pixel_deg * 110.574,
        grid.pixel_deg * 111.32 * np.cos(np.deg2rad(grid.lats().mean())),
    )
    areas, names = protected.read(raw_dir)
    distance_km, nearest = {}, {}
    for kind, ids in areas.items():
        distance, (rows, cols) = ndimage.distance_transform_edt(
            ids == 0, sampling=cell_km, return_indices=True
        )
        distance_km[kind] = distance if ids.any() else np.full(ids.shape, np.inf)
        nearest[kind] = ids[rows, cols]
    cover = landcover.read_year(cover_year, raw_dir)
    return Layers(grid, cover, people_near, distance_km, nearest, names)


def cover_year(event_year: int) -> int:
    """Return the land cover year for an event: the year before it, if the map has that year."""
    return min(event_year - 1, config.LANDCOVER_LAST_YEAR)


def cover_groups(classes: np.ndarray) -> np.ndarray:
    """Return the group name of each land cover class in an array."""
    names = np.full(256, "other", dtype="U9")
    for name, members in config.COVER_GROUPS.items():
        names[list(members)] = name
    return names[classes]


def facts(
    lat: np.ndarray, lon: np.ndarray, frp_mw: np.ndarray, advance_m: float | None, layers: Layers
) -> dict:
    """Return the facts of an event from its detections and from the layers.

    `frp_mw` has NaN for a detection with no fire power. `advance_m` is the advance of the
    newest step, or None for no measured advance.
    """
    rows, cols = layers.grid.rows_cols(lat, lon)
    classes = layers.cover[rows, cols]
    # A cell with the class 0 has no land cover: it is not in the map. It does not count.
    groups, counts = np.unique(cover_groups(classes[classes > 0]), return_counts=True)
    north_km = (lat.max() - lat.min()) * 110.574
    east_km = (lon.max() - lon.min()) * 111.32 * float(np.cos(np.deg2rad(lat.mean())))
    found = {
        "detections": len(lat),
        "max_frp_mw": None if np.isnan(frp_mw).all() else float(np.nanmax(frp_mw)),
        "extent_km": float(max(north_km, east_km)),
        "advance_m": advance_m,
        "cover": str(groups[counts.argmax()]) if len(groups) else None,
        "cover_share": float(counts.max() / counts.sum()) if len(groups) else None,
        "people_near": float(layers.people_near[rows, cols].max()),
    }
    for kind, distance in layers.distance_km.items():
        at = distance[rows, cols].argmin()
        site = int(layers.nearest[kind][rows[at], cols[at]])
        found[f"{kind}_km"] = float(distance[rows[at], cols[at]])
        found[f"{kind}_name"] = layers.names.get(site)
    return found


def step_points(value: float | None, steps: tuple | None, points: float) -> float:
    """Return the points of a value: an equal part of the points for each step that it reaches."""
    if value is None or steps is None:
        return 0.0
    return points * sum(value >= step for step in steps) / len(steps)


def score(found: dict) -> tuple[float, dict[str, float]]:
    """Return the severity of an event from its facts, and the points of each part."""
    land_km = min(found["indigenous_km"], found["protected_km"])
    if land_km == 0:
        land = config.SEVERITY_LAND_POINTS
    else:
        land = config.SEVERITY_LAND_NEAR_POINTS if land_km <= config.SEVERITY_NEAR_KM else 0
    parts = {
        "power": step_points(
            found["max_frp_mw"], config.SEVERITY_POWER_STEPS_MW, config.SEVERITY_POWER_POINTS
        ),
        "extent": step_points(
            found["extent_km"], config.SEVERITY_EXTENT_STEPS_KM, config.SEVERITY_EXTENT_POINTS
        ),
        "advance": step_points(
            found["advance_m"], config.SEVERITY_ADVANCE_STEPS_M, config.SEVERITY_ADVANCE_POINTS
        ),
        "cover": float(config.SEVERITY_COVER_POINTS.get(found["cover"], 0)),
        "people": step_points(
            found["people_near"], config.SEVERITY_PEOPLE_STEPS, config.SEVERITY_PEOPLE_POINTS
        ),
        "land": float(land),
    }
    return sum(parts.values()), parts
