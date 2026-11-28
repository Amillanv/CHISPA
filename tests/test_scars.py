"""Tests of the border mask and of the scar search, with cases small enough for paper."""

import numpy as np

from chispa.grid import Grid
from chispa.sources.border import contains, rasterize
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


def test_position_is_in_the_border_if_its_pixel_is_in_the_raster():
    # A polygon with a hole and with edges that are not on the pixel edges.
    rings = [square(0.3, 0.2, 5.6, 5.1), square(2.2, 2.4, 3.9, 4.3)]
    mask = rasterize(rings, GRID)
    rows, cols = np.indices(mask.shape)
    # Some positions in each pixel, not only the centres: the answer is that of the pixel.
    for part in (0.1, 0.5, 0.9):
        lat = GRID.north - (rows.ravel() + part) * GRID.pixel_deg
        lon = GRID.west + (cols.ravel() + 1 - part) * GRID.pixel_deg
        assert (contains(rings, GRID, lat, lon) == mask.ravel()).all()
    # A position off the grid is not in the border.
    assert contains(rings, GRID, np.array([GRID.north + 1.0]), np.array([GRID.west])).tolist() == [
        False
    ]


def test_pixels_that_touch_in_the_same_month_are_one_scar():
    months = np.zeros((6, 6), dtype=np.uint8)
    months[0, 0] = months[1, 1] = 8  # touch at a corner: one scar
    months[1, 2] = 9  # touches the first scar but burned in a different month
    months[5, 5] = 8  # far away: a different scar
    numbers = find_scars(months)
    assert numbers[0, 0] == numbers[1, 1] == 1
    assert (numbers[5, 5], numbers[1, 2]) == (2, 3)
    assert (numbers > 0).sum() == 4
