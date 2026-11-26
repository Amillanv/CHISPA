"""Tests of the Monitor map of a year against a small real piece: 20 pixels of 2025."""

from datetime import UTC, datetime
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


def test_each_month_has_the_time_when_its_image_last_changed():
    found = monitor.read_published(2025, SAMPLES)
    # The file is that of the asset on 2026-11-26: the image of December came on 12 January.
    assert sorted(found) == list(range(1, 13))
    assert found[12].replace(microsecond=0) == datetime(2026, 1, 12, 15, 9, 0, tzinfo=UTC)
    with pytest.raises(RuntimeError, match="chispa fetch monitor --year 2024"):
        monitor.read_published(2024, SAMPLES)
