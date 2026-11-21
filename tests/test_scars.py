"""Tests of the border mask and of the scar search, with cases small enough for paper."""

import numpy as np

from chispa.grid import Grid
from chispa.sources.border import rasterize
from chispa.sources.burnday import scar_burn_days
from chispa.sources.scars import find_scars

# A grid of 6 x 6 pixels of 1 degree. The north-west corner is at lon 0, lat 6.
GRID = Grid(west=0.0, north=6.0, pixel_deg=1.0, width=6, height=6)


def square(west, south, east, north):
    return np.array([[west, south], [east, south], [east, north], [west, north], [west, south]])


def test_mask_of_a_square():
    mask = rasterize([square(1, 1, 4, 4)], GRID)
    assert mask.sum() == 9
    assert mask[2:5, 1:4].all()  # lat 1 to 4 is rows 2 to 4. lon 1 to 4 is columns 1 to 3.


def test_hole_stays_out_of_the_mask():
    mask = rasterize([square(0, 0, 6, 6), square(2, 2, 4, 4)], GRID)
    assert mask.sum() == 36 - 4
    assert not mask[2:4, 2:4].any()


def test_pixels_that_touch_in_the_same_month_are_one_scar():
    months = np.zeros((6, 6), dtype=np.uint8)
    months[0, 0] = months[1, 1] = 8  # touch at a corner: one scar
    months[1, 2] = 9  # touches the first scar but burned in a different month
    months[5, 5] = 8  # far away: a different scar
    scars, numbers = find_scars(months, GRID, 2024)
    assert [(s.number, s.month) for s in scars] == [(1, 8), (2, 8), (3, 9)]
    assert numbers[0, 0] == numbers[1, 1] == 1
    assert (numbers[5, 5], numbers[1, 2]) == (2, 3)
    assert (numbers > 0).sum() == 4


def test_scar_position_and_box():
    months = np.zeros((6, 6), dtype=np.uint8)
    months[0, 0] = months[1, 1] = 8
    scar = find_scars(months, GRID, 2024)[0][0]
    assert (scar.lat, scar.lon) == (5.0, 1.0)  # the mean of (5.5, 0.5) and (4.5, 1.5)
    assert (scar.south, scar.west, scar.north, scar.east) == (4.0, 0.0, 6.0, 2.0)


def test_scar_area_is_the_sum_of_the_pixel_areas():
    months = np.zeros((6, 6), dtype=np.uint8)
    months[5, 0] = 3  # one pixel of 1 degree, with its centre at lat 0.5
    scar = find_scars(months, GRID, 2024)[0][0]
    expected_ha = 111_320 * np.cos(np.deg2rad(0.5)) * 110_574 / 1e4
    assert abs(scar.area_ha - expected_ha) < 1e-6


def test_burn_days_of_a_scar(monkeypatch):
    monkeypatch.setattr("chispa.config.EVAL_MONTHS_BEFORE", 1)
    # The burn day grid has 2 x 2 pixels of 3 degrees on the same area as GRID.
    coarse = Grid(west=0.0, north=6.0, pixel_deg=3.0, width=2, height=2)
    days = np.zeros((12, 2, 2), dtype=np.uint16)
    days[7, 0, 0] = 220  # August layer, north-west pixel
    days[6, 0, 1] = 200  # July layer, north-east pixel
    days[5, 1, 0] = 170  # June layer, south-west pixel
    months = np.zeros((6, 6), dtype=np.uint8)
    numbers = np.zeros((6, 6), dtype=np.int32)
    months[0, 0], numbers[0, 0] = 8, 1  # scar 1: one pixel in the north-west, one in the north-east
    months[0, 5], numbers[0, 5] = 8, 1
    months[5, 0], numbers[5, 0] = 8, 2  # scar 2: August, but the only burn day is in June
    first, last = scar_burn_days(numbers, months, GRID, days, coarse, count=2)
    assert (first[1], last[1]) == (200, 220)  # the July day counts: one month before
    assert (first[2], last[2]) == (0, 0)  # June is two months before: no burn day
