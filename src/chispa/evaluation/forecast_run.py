"""The run of the growth forecast: each year gets the models of the other years.

A year of the development years gets the models of the other development years. A test run also
scores each test year one time, with the models of all development years.
`docs/method.md` section 11.28 gives the rules.
"""

from pathlib import Path

import numpy as np

from chispa import confidence, config, forecast_model
from chispa.evaluation import forecast, forecast_say
from chispa.grid import pantanal_grid
from chispa.sources import border

TABLES = ("forecast", "forecast_direction", "forecast_inputs")
TABLES += ("forecast_chances", "forecast_sectors", "forecast_first_look", "forecast_periods")
# The name of each size of front in a table, and True for the small fronts (`config.py`).
SIZES = {"3 or more": False, "1 or 2": True}
JOINED = ("x", "y", "small")


def training(cases: dict, years: tuple[int, ...], key: tuple[str, int]) -> dict:
    """Return the rows of one question from the training years, with the year of each row."""
    found = {name: np.concatenate([cases[year][key][name] for year in years]) for name in JOINED}
    of_row = np.concatenate([np.full(len(cases[year][key]["y"]), year) for year in years])
    return found | {"years": of_row}


def year_cases(rows: dict[int, dict]) -> dict[int, dict]:
    """Return the rows of each question and each window, for each year."""
    return {
        year: {
            (question, hours): forecast.case(of_year, question, hours)
            for question in forecast_model.QUESTIONS
            for hours in config.FRONT_WINDOWS_H
        }
        for year, of_year in rows.items()
    }


def _models(train: dict, held: dict) -> tuple[dict[str, np.ndarray], object]:
    """Return the chances of the regression and of the trees for the held rows, and the trees.

    The trees read an absent value as absent. The regression cannot: it gets the mean of the
    training rows in its place.
    """
    trees = forecast_model.fit_trees(train["x"], train["y"], train["years"])
    mean = np.nanmean(train["x"], axis=0)
    filled = [np.where(np.isnan(table), mean, table) for table in (train["x"], held["x"])]
    regression = confidence.fit(filled[0], train["y"], held["names"])
    chances = {"regression": confidence.probability(regression, filled[1])}
    chances["trees"] = trees.predict_proba(held["x"])[:, 1]
    return chances, trees


def _scores(key: tuple[str, int], train: dict, held: dict, chances: dict) -> list[dict]:
    """Return the scores of one question, for each size of front."""
    found = []
    for size, small in SIZES.items():
        part, share = held["small"] == small, float(train["y"][train["small"] == small].mean())
        rows = {name: held[name][part] for name in ("y", "persistence", "wind") if name in held}
        of_size = {name: chance[part] for name, chance in chances.items()}
        row = {"question": key[0], "hours": key[1], "size": size}
        found.append(row | forecast.scores(rows, of_size, share))
    return found


def _counts(of_year: dict, hours: int, held: dict, trees: dict) -> dict[str, list[dict]]:
    """Return the tables of what the trees say, for the fronts that are not small.

    `held` has the rows of the sector question. `trees` has the chances of each question, and
    the persistence value of each front.
    """
    large = ~held["small"][:: config.FRONT_SECTORS]
    use = held["fronts"].copy()
    use[use] = large
    chances = {name: trees[name][large] for name in ("new_ground", "persistence")}
    chances["sector"] = trees["sector"].reshape(-1, config.FRONT_SECTORS)[large].ravel()
    sectors = forecast_say.sector_row(of_year["answers"], hours, use, chances["sector"])
    first = forecast_say.first_look_rows(of_year, hours, use, chances)
    periods = forecast_say.period_rows(of_year, hours, use, chances)
    return {
        "forecast_sectors": [sectors],
        "forecast_first_look": first,
        "forecast_periods": periods,
    }


def year_tables(rows: dict, cases: dict, year: int, training_years: tuple[int, ...]) -> dict:
    """Return the tables of one year, from models that did not read that year."""
    tables = {name: [] for name in TABLES}
    for hours in config.FRONT_WINDOWS_H:
        trees = {}
        for question in forecast_model.QUESTIONS:
            key = (question, hours)
            train, held = training(cases, training_years, key), cases[year][key]
            chances, model = _models(train, held)
            trees[question] = chances["trees"]
            tables["forecast"] += _scores(key, train, held, chances)
            tables["forecast_inputs"] += forecast.effect_rows(model, held, key)
            large = ~held["small"]
            tables["forecast_chances"] += forecast_say.chance_rows(
                key, chances["trees"][large], held["y"][large]
            )
            for size, small in SIZES.items() if question == "sector" else ():
                row = forecast.direction_row(rows[year], held, chances, (hours, small))
                tables["forecast_direction"].append({"size": size} | row)
        trees["persistence"] = cases[year][("new_ground", hours)]["persistence"]
        # The rows of the three questions of one window are the same fronts.
        for name, found in _counts(rows[year], hours, held, trees).items():
            tables[name] += found
    return tables


def forecast_tables(store_path: Path, raw_dir: Path, test_run: bool) -> dict[int, dict]:
    """Return the tables of each development year, and of each test year in a test run."""
    rings = border.read_rings(raw_dir / "border" / "pantanal.geojson")
    in_biome = border.rasterize(rings, pantanal_grid())
    years = config.FRONT_YEARS + (config.FRONT_TEST_YEARS if test_run else ())
    rows = {year: forecast.year_rows(year, store_path, raw_dir, in_biome) for year in years}
    del in_biome
    cases = year_cases(rows)
    tables = {}
    for year in years:
        training = tuple(other for other in config.FRONT_YEARS if other != year)
        tables[year] = year_tables(rows, cases, year, training)
    return tables
