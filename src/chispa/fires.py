"""Group burned pixels into fires. A fire is the unit of the evaluation.

The burn scar map cuts one fire into many scars, because it splits a burn by image month.
The burn day product says when each cell of approximately 445 m burned.
Burned cells that touch and burned in near days are one fire.
"""

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from chispa import config
from chispa.grid import Grid
from chispa.models import Fire


def find_fires(
    months: np.ndarray, scars: np.ndarray, fine: Grid, days: np.ndarray, coarse: Grid
) -> tuple[list[Fire], np.ndarray]:
    """Return the fires, and a grid that holds the fire number of each pixel (0 for no fire).

    `months` and `scars` are grids of 30 m: the burn month and the scar number of each pixel.
    `days` has one layer for each month on the coarse grid: the burn day of each cell.
    """
    rows, cols = np.nonzero(scars)
    if len(rows) == 0:
        return [], np.zeros(scars.shape, dtype=np.int32)
    month = months[rows, cols].astype(int)
    lats = fine.lats()[rows]
    day, cell = _pixel_days(month, lats, fine.lons()[cols], days, coarse)
    fire = _join_scars(_join_cells(cell, day, coarse.width), scars[rows, cols].astype(np.int64))
    # The area of a pixel in hectares. It gets smaller away from the equator.
    area_ha = (
        (fine.pixel_deg * 111_320 * np.cos(np.deg2rad(lats))) * (fine.pixel_deg * 110_574) / 1e4
    )
    numbers = np.zeros(scars.shape, dtype=np.int32)
    numbers[rows, cols] = fire
    return _measure(fire, area_ha, day, month), numbers


def _pixel_days(
    month: np.ndarray, lats: np.ndarray, lons: np.ndarray, days: np.ndarray, coarse: Grid
) -> tuple[np.ndarray, np.ndarray]:
    """Return the burn day (0 for none) and the coarse cell of each burned pixel.

    We read the burn day of the map month. If that month has no burn day, we read the
    months before it (`config.py` gives how many). The map month is frequently late.
    """
    rows, cols = coarse.rows_cols(lats, lons)
    inside = (rows >= 0) & (rows < coarse.height) & (cols >= 0) & (cols < coarse.width)
    day = np.zeros(len(month), dtype=int)
    for back in range(config.EVAL_MONTHS_BEFORE + 1):
        layer = month - 1 - back
        usable = inside & (day == 0) & (layer >= 0)
        day[usable] = days[layer[usable], rows[usable], cols[usable]]
    return day, rows * coarse.width + cols


def _join_cells(cell: np.ndarray, day: np.ndarray, width: int) -> np.ndarray:
    """Return a fire number for each pixel with a burn day, and 0 for the other pixels.

    Two cells are one fire if they touch, also at a corner, and their first burn days
    are not farther apart than the day margin.
    """
    known = day > 0
    fire = np.zeros(len(day), dtype=np.int64)
    if not known.any():
        return fire
    cells, index = np.unique(cell[known], return_inverse=True)
    first = np.full(len(cells), 999)
    np.minimum.at(first, index, day[known])
    links = []
    for step in (1, width - 1, width, width + 1):  # east, south-west, south, south-east
        other = np.minimum(np.searchsorted(cells, cells + step), len(cells) - 1)
        near = (
            (cells[other] == cells + step)
            & (np.abs(cells[other] % width - cells % width) <= 1)  # not across a grid edge
            & (np.abs(first[other] - first) <= config.EVAL_DAY_MARGIN)
        )
        links.append(np.stack([np.nonzero(near)[0], other[near]]))
    start, end = np.concatenate(links, axis=1)
    graph = coo_matrix((np.ones(len(start), dtype=bool), (start, end)), shape=(len(cells),) * 2)
    fire[known] = connected_components(graph, directed=False)[1][index] + 1
    return fire


def _join_scars(fire: np.ndarray, scar: np.ndarray) -> np.ndarray:
    """Give a fire number to each pixel that has no burn day.

    Such a pixel goes to the fire that holds most of the dated pixels of its scar.
    A scar with no dated pixel becomes one fire. That fire has only a month.
    """
    count = int(fire.max())
    known = fire > 0
    pair, size = np.unique(scar[known] * (count + 1) + fire[known], return_counts=True)
    order = np.argsort(size, kind="stable")
    main = np.zeros(int(scar.max()) + 1, dtype=np.int64)
    # NumPy writes in sequence, thus the largest fire of each scar stays.
    main[pair[order] // (count + 1)] = pair[order] % (count + 1)
    fire = np.where(known, fire, main[scar])
    alone = np.unique(scar[fire == 0])
    number = np.zeros(len(main), dtype=np.int64)
    number[alone] = count + 1 + np.arange(len(alone))
    return np.where(fire > 0, fire, number[scar])


def _measure(
    fire: np.ndarray, area_ha: np.ndarray, day: np.ndarray, month: np.ndarray
) -> list[Fire]:
    count = int(fire.max())
    total_ha = np.bincount(fire, weights=area_ha, minlength=count + 1)
    known = day > 0
    first = np.full(count + 1, 999)
    last = np.zeros(count + 1, dtype=int)
    np.minimum.at(first, fire[known], day[known])
    np.maximum.at(last, fire[known], day[known])
    # A fire with no burn day is one scar, thus all its pixels have the same month.
    months = np.zeros(count + 1, dtype=int)
    months[fire] = month
    return [
        Fire(
            number=number,
            area_ha=float(total_ha[number]),
            month=None if last[number] else int(months[number]),
            first_burn_day=int(first[number]) if last[number] else None,
            last_burn_day=int(last[number]) if last[number] else None,
        )
        for number in range(1, count + 1)
    ]
