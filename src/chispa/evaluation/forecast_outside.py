"""The growth forecast for the fronts in Brazil outside the biome: the trees of the biome there.

The trees learn from the fronts of the biome (`forecast_run.py`). The store has the detections
of the whole box, and a fire near the biome gets an alert also. Its fronts have the same
inputs: the maps are those of Brazil. This module scores the trees of the biome on the fronts
in Brazil outside it. No tree reads such a front.
`docs/method.md` section 11.33 gives the rules.
"""

from pathlib import Path

import numpy as np

from chispa import config
from chispa.evaluation import forecast, forecast_run
from chispa.grid import pantanal_grid
from chispa.sources import border, landcover

# The tables of `forecast_run.py` that this run keeps, with their names for these fronts.
TABLES = {"forecast": "forecast_outside", "forecast_direction": "forecast_direction_outside"}


def brazil(raw_dir: Path) -> np.ndarray:
    """Return True for each pixel of the Pantanal grid in a cell with a land cover class.

    The land cover map has Brazil only: a cell of a different country has no class.
    """
    grid, cells = pantanal_grid(), config.LAYER_CELLS
    has = landcover.read_year(config.LANDCOVER_LAST_YEAR, raw_dir) > 0
    return np.repeat(np.repeat(has, cells, axis=0), cells, axis=1)[: grid.height, : grid.width]


def _part(rows: dict, keep: np.ndarray) -> dict:
    """Return the answers and the inputs of the fronts of `keep`."""
    return {
        kind: {name: values[keep] for name, values in found.items()} for kind, found in rows.items()
    }


def year_parts(store_path: Path, raw_dir: Path, years: tuple[int, ...]) -> tuple[dict, dict]:
    """Return the rows of the fronts of each year in the biome, and of those in Brazil outside it.

    A front is in the biome if its centre is in the border, as in each other result.
    """
    grid = pantanal_grid()
    rings = border.read_rings(raw_dir / "border" / "pantanal.geojson")
    in_biome = border.rasterize(rings, grid)
    counted = brazil(raw_dir) | in_biome
    inside, outside = {}, {}
    for year in years:
        rows = forecast.year_rows(year, store_path, raw_dir, counted)
        own = in_biome[grid.rows_cols(rows["answers"]["lat"], rows["answers"]["lon"])]
        inside[year], outside[year] = _part(rows, own), _part(rows, ~own)
    return inside, outside


def outside_tables(store_path: Path, raw_dir: Path, test_run: bool) -> dict[int, dict]:
    """Return the tables of the fronts outside the biome of each development year, and of each
    test year in a test run.

    The trees of a year come from the fronts of the biome of the other development years, as in
    `forecast_run.py`: they are the same trees.
    """
    years = config.FRONT_YEARS + (config.FRONT_TEST_YEARS if test_run else ())
    inside, outside = year_parts(store_path, raw_dir, years)
    cases, held = forecast_run.year_cases(inside), forecast_run.year_cases(outside)
    tables = {}
    for year in years:
        training = tuple(other for other in config.FRONT_YEARS if other != year)
        found = forecast_run.year_tables(outside, cases | {year: held[year]}, year, training)
        tables[year] = {new: found[name] for name, new in TABLES.items()}
    return tables
