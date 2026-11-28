"""Tests of the Monitor map of a year against a small real piece: 20 pixels of 2025."""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
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


def test_map_of_one_month_comes_from_the_folder_of_that_month(tmp_path):
    import shutil

    shutil.copytree(SAMPLES / "monitor" / "2025-12", tmp_path / "monitor" / "2025-12")
    later = tmp_path / "monitor" / "2025-13"
    later.mkdir()
    # A later folder for the year, with a tile that has a different value for each pixel.
    for path in (SAMPLES / "monitor" / "2025-12").glob("r*_c*.npz"):
        tile = np.load(path)["month"]
        np.savez_compressed(later / path.name, month=np.full_like(tile, 7))
    # A folder is a map only with the file that a download writes last.
    assert monitor.read_year(2025, tmp_path, GRID)[1] == 12
    shutil.copy(SAMPLES / "monitor" / "2025-12" / "published.json", later / "published.json")
    newest, last = monitor.read_year(2025, tmp_path, GRID)
    assert last == 13 and (newest == 7).all()
    pinned, last = monitor.read_year(2025, tmp_path, GRID, month=12)
    assert last == 12 and pinned[1].tolist() == [12, 12, 0, 0, 0]
    # A month with no folder of its own: the newest folder is read.
    assert monitor.read_year(2025, tmp_path, GRID, month=6)[1] == 13


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
