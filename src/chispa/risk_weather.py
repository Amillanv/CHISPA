"""The weather of the days before a live alert, at its place.

The growth risk reads the rain, the wind and the dryness of the air of the days before an alert
(`risk.py`). ERA5-Land has them, some days late. This module reads the days on disk. If a day
is absent, it gets the files of ERA5-Land again. For a day that ERA5-Land does not have yet, it
gets the IFS values of Open-Meteo for the weather cell of each alert. Thus no person must get
the weather before an alert can have its answer.
IFS is a different model: its levels are not those of ERA5-Land (`docs/sources.md` section 8.4).
"""

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import ee
import numpy as np

from chispa.sources import openmeteo, weather

Cell = tuple[int, int]  # The row and the column of a cell of the weather grid.


@dataclass(frozen=True)
class Days:
    """The weather for some alerts: ERA5-Land from a first day, then Open-Meteo for some cells."""

    start: date
    era5: dict[str, np.ndarray]  # Each measure: days, rows, columns.
    later: dict[Cell, dict[str, np.ndarray]]  # Each measure of the days after ERA5-Land.
    note: str | None  # Why the files of ERA5-Land did not come again, if we asked for them.


def _on_disk(raw_dir: Path, start: date, need: date) -> tuple[dict[str, np.ndarray], date]:
    """Return the ERA5-Land days on disk from a first day of a month, and the last of them."""
    days, _ = weather.read_newest(raw_dir, start, need)
    return days, start + timedelta(days=len(days["rain_mm"]) - 1)


def _pull(raw_dir: Path, have: date, need: date, project: str) -> str | None:
    """Get the files of ERA5-Land again if the product has a later day than the files.

    Return the reason if Earth Engine gave no answer: the days then come from Open-Meteo.
    """
    try:
        if weather.has_day(have + timedelta(days=1), project):
            for year in sorted({(have + timedelta(days=1)).year, need.year}):
                weather.download_year(year, project, raw_dir)
    except (ee.EEException, OSError) as error:
        return f"Earth Engine gave no weather: {type(error).__name__}"
    return None


def load(raw_dir: Path, first: date, need: date, cells: set[Cell], project: str | None) -> Days:
    """Return the weather from the month of the day `first` to the day `need`, for some cells.

    `project` is the project of Earth Engine, or None: then this gets no file of ERA5-Land.
    """
    start, note = first.replace(day=1), None
    era5, have = _on_disk(raw_dir, start, need)
    if have < need and project:
        note = _pull(raw_dir, have, need, project)
        era5, have = _on_disk(raw_dir, start, need)
    later = {}
    if have < need:
        grid, order = weather.weather_grid(), sorted(cells)
        lats = grid.lats()[[row for row, _ in order]]
        lons = grid.lons()[[col for _, col in order]]
        span = (have + timedelta(days=1), need)
        found, _ = openmeteo.read(openmeteo.download(lats, lons, span, raw_dir))
        later = {
            cell: {name: values[place] for name, values in found.items()}
            for place, cell in enumerate(order)
        }
    cut = (need - start).days + 1
    return Days(start, {name: layer[:cut] for name, layer in era5.items()}, later, note)


def series(days: Days, cell: Cell) -> tuple[dict[str, np.ndarray], int]:
    """Return each measure of each day at one cell, and its number of days from ERA5-Land.

    The days after that number are from Open-Meteo.
    """
    found = {name: layer[:, cell[0], cell[1]] for name, layer in days.era5.items()}
    more, count = days.later.get(cell), len(found["rain_mm"])
    if more is None:
        return found, count
    return {name: np.concatenate([values, more[name]]) for name, values in found.items()}, count
