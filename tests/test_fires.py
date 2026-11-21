"""Tests of the fire search, with cases small enough for paper."""

import numpy as np

from chispa.fires import find_fires
from chispa.grid import Grid

# A grid of 6 x 6 pixels of 1 degree, and a burn day grid of 3 x 3 cells of 2 degrees
# on the same area. Thus each cell holds 2 x 2 pixels.
FINE = Grid(west=0.0, north=6.0, pixel_deg=1.0, width=6, height=6)
COARSE = Grid(west=0.0, north=6.0, pixel_deg=2.0, width=3, height=3)


def august(*pixels):
    """A month grid and a scar grid: each pixel is a scar of August with its own number."""
    months = np.zeros((6, 6), dtype=np.uint8)
    scars = np.zeros((6, 6), dtype=np.int32)
    for number, pixel in enumerate(pixels, start=1):
        months[pixel], scars[pixel] = 8, number
    return months, scars


def burn_days(**cells):
    """The burn day grid of August. `r0c1=220` puts day 220 in row 0, column 1."""
    days = np.zeros((12, 3, 3), dtype=np.uint16)
    for name, day in cells.items():
        days[7, int(name[1]), int(name[3])] = day
    return days


def test_cells_that_touch_and_burned_in_near_days_are_one_fire(monkeypatch):
    monkeypatch.setattr("chispa.config.EVAL_DAY_MARGIN", 7)
    months, scars = august((0, 0), (0, 2), (0, 4))  # one pixel in each cell of the north row
    fires, numbers = find_fires(
        months, scars, FINE, burn_days(r0c0=220, r0c1=227, r0c2=235), COARSE
    )
    # West and centre: 7 days apart, one fire. Centre and east: 8 days apart, two fires.
    assert numbers[0, 0] == numbers[0, 2] != numbers[0, 4]
    days = sorted((fire.first_burn_day, fire.last_burn_day, fire.month) for fire in fires)
    assert days == [(220, 227, None), (235, 235, None)]


def test_cells_that_do_not_touch_are_two_fires():
    months, scars = august((0, 0), (0, 4))  # the centre cell of the north row did not burn
    fires, numbers = find_fires(months, scars, FINE, burn_days(r0c0=220, r0c2=220), COARSE)
    assert len(fires) == 2
    assert numbers[0, 0] != numbers[0, 4]


def test_pixel_with_no_burn_day_goes_to_the_fire_of_its_scar():
    months, scars = august((0, 0), (0, 2))
    scars[0, 2] = 1  # the two pixels are one scar, but only the west cell has a burn day
    fires, numbers = find_fires(months, scars, FINE, burn_days(r0c0=220), COARSE)
    assert len(fires) == 1
    assert numbers[0, 0] == numbers[0, 2] == 1


def test_scar_with_no_burn_day_is_a_fire_with_only_a_month():
    months, scars = august((0, 0), (5, 5))
    fires, numbers = find_fires(months, scars, FINE, burn_days(r0c0=220), COARSE)
    assert (fires[0].first_burn_day, fires[0].month) == (220, None)
    assert (fires[1].first_burn_day, fires[1].last_burn_day, fires[1].month) == (None, None, 8)
    assert numbers[5, 5] == 2


def test_burn_day_of_the_month_before_counts(monkeypatch):
    monkeypatch.setattr("chispa.config.EVAL_MONTHS_BEFORE", 1)
    months, scars = august((0, 0), (5, 5))
    days = np.zeros((12, 3, 3), dtype=np.uint16)
    days[6, 0, 0] = 200  # July: one month before the map month
    days[5, 2, 2] = 170  # June: two months before
    fires, _ = find_fires(months, scars, FINE, days, COARSE)
    assert [(fire.first_burn_day, fire.month) for fire in fires] == [(200, None), (None, 8)]


def test_fire_area_is_the_sum_of_the_pixel_areas():
    months, scars = august((5, 0))  # one pixel of 1 degree, with its centre at lat 0.5
    fires, _ = find_fires(months, scars, FINE, burn_days(), COARSE)
    expected_ha = 111_320 * np.cos(np.deg2rad(0.5)) * 110_574 / 1e4
    assert abs(fires[0].area_ha - expected_ha) < 1e-6
