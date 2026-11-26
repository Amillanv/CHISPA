"""Tests of the Monitor map of a year against a small real piece: 20 pixels of 2025."""

from pathlib import Path

import pytest

from chispa.grid import Grid
from chispa.sources import monitor

SAMPLES = Path(__file__).parent / "samples"
GRID = Grid(west=0.0, north=0.0, pixel_deg=0.001, width=5, height=4)


def test_month_grid_has_the_first_month_with_a_burn():
    months, last = monitor.read_year(2025, SAMPLES, GRID)
    # The folder name says that the map had the months to December.
    assert last == 12
    # Pixels with no burn, pixels of December and pixels of January, as the map gave them.
    assert months.tolist() == [
        [0, 0, 0, 0, 0],
        [12, 12, 0, 0, 0],
        [12, 12, 0, 0, 0],
        [12, 12, 1, 1, 1],
    ]


def test_year_with_no_folder_says_what_to_do():
    with pytest.raises(RuntimeError, match="chispa fetch monitor --year 2024"):
        monitor.read_year(2024, SAMPLES, GRID)


def test_tiles_that_do_not_cover_the_grid_are_an_error():
    larger = Grid(west=0.0, north=0.0, pixel_deg=0.001, width=6, height=4)
    with pytest.raises(RuntimeError, match="do not cover the grid"):
        monitor.read_year(2025, SAMPLES, larger)
