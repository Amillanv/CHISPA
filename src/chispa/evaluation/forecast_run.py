"""The run of the growth forecast: each year gets the models of the other years.

A year of the development years gets the models of the other development years. A test run also
scores each test year one time, with the models of all development years.
`docs/method.md` section 11.28 gives the rules.
"""

from pathlib import Path

import numpy as np

from chispa import confidence, config
from chispa.evaluation import forecast, forecast_say
from chispa.grid import pantanal_grid
from chispa.sources import border

TABLES = ("forecast", "forecast_direction", "forecast_inputs")
TABLES += ("forecast_chances", "forecast_sectors", "forecast_first_look")


def training(cases: dict, years: tuple[int, ...], key: tuple[str, int]) -> dict:
    """Return the rows of one question from the training years, with the year of each row."""
    table = np.concatenate([cases[year][key]["x"] for year in years])
    label = np.concatenate([cases[year][key]["y"] for year in years])
    of_row = np.concatenate([np.full(len(cases[year][key]["y"]), year) for year in years])
    return {"x": table, "y": label, "years": of_row}


def year_cases(rows: dict[int, dict]) -> dict[int, dict]:
    """Return the rows of each question and each window, for each year."""
    return {
        year: {
            (question, hours): forecast.case(of_year, question, hours)
            for question in forecast.QUESTIONS
            for hours in config.FRONT_WINDOWS_H
        }
        for year, of_year in rows.items()
    }


def year_tables(rows: dict, cases: dict, year: int, training_years: tuple[int, ...]) -> dict:
    """Return the tables of one year, from models that did not read that year."""
    tables = {name: [] for name in TABLES}
    for hours in config.FRONT_WINDOWS_H:
        trees = {}
        for question in forecast.QUESTIONS:
            key = (question, hours)
            train, held = training(cases, training_years, key), cases[year][key]
            model = forecast.fit_trees(train["x"], train["y"], train["years"])
            regression = confidence.fit(train["x"], train["y"], held["names"])
            chances = {"regression": confidence.probability(regression, held["x"])}
            chances["trees"] = trees[question] = model.predict_proba(held["x"])[:, 1]
            found = forecast.scores(held, chances, float(train["y"].mean()))
            tables["forecast"].append({"question": question, "hours": hours} | found)
            tables["forecast_inputs"] += forecast.effect_rows(model, held, key)
            tables["forecast_chances"] += forecast_say.chance_rows(key, trees[question], held["y"])
            if question == "sector":
                row = forecast.direction_row(rows[year], hours, held, chances)
                tables["forecast_direction"].append(row)
        # The rows of the three questions of one window are the same fronts.
        use, answers = held["fronts"], rows[year]["answers"]
        tables["forecast_sectors"].append(
            forecast_say.sector_row(answers, hours, use, trees["sector"])
        )
        tables["forecast_first_look"] += forecast_say.first_look_rows(rows[year], hours, use, trees)
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
