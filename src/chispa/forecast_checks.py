"""The commands of the growth forecast: its tables, its saved trees, the live forecast, its score.

`chispa forecast` has one run for each option. They are not in `checks.py`, which has the
commands of the other parts: a file has a limit of lines.
"""

import json
from datetime import UTC, datetime

from chispa import config, forecast_files, forecast_live
from chispa.evaluation import forecast_outside, forecast_score, forecast_trees, front_chance
from chispa.evaluation.forecast_run import forecast_tables
from chispa.evaluation.report import write_summary, write_tables

# The options of `chispa forecast` that select a different run, with the text of their help.
ACTIONS = {
    "live": "Forecast the newest fronts.",
    "trees": "Fit and save the live trees.",
    "score": "Score the saved live forecasts.",
    "outside": "Score the trees on the fronts in Brazil outside the biome.",
    "front-chance": "Score the chance of a front for an alert of GOES only, and save its model.",
}


def _live() -> None:
    """Give the forecast of the fronts of the newest looks as JSON, and save its files."""
    looks = forecast_live.live_looks(config.STORE_PATH, config.RAW_DIR, datetime.now(UTC))
    if looks is None:
        raise SystemExit("No saved trees are those of now. Run `chispa forecast --trees` first.")
    forecast_files.save(looks, config.FORECAST_LIVE_DIR, datetime.now(UTC))
    print(json.dumps({"hours": config.FORECAST_LIVE_HOURS, "looks": looks}, indent=2))


def run(action: str | None, test_run: bool) -> None:
    """Do one run of `chispa forecast`.

    No option: the tables of each development year, from the models of the other years. A test
    run also makes the tables of the test years, one time, from the models of all development
    years. `outside` makes those tables for the fronts in Brazil outside the biome.
    `trees` fits the trees of all development years, and saves them for the live forecast.
    `live` makes no table: it gives the forecast of the fronts of the newest looks.
    `score` makes the table of the saved live forecasts against what came.
    `front-chance` makes the tables of the chance of a front for an alert that only GOES started,
    and it saves the model of all development years for the live chance.
    """
    arguments = (config.STORE_PATH, config.RAW_DIR)
    if action == "trees":
        print(f"forecast: the saved trees have the mark {forecast_trees.fit(*arguments)}.")
        return
    if action == "live":
        _live()
        return
    if action == "score":
        tables = forecast_score.score_tables(*arguments, datetime.now(UTC))
    elif action == "outside":
        tables = forecast_outside.outside_tables(*arguments, test_run)
    elif action == "front-chance":
        tables = front_chance.chance_tables(*arguments, test_run)
    else:
        tables = forecast_tables(*arguments, test_run)
    if not tables:
        raise SystemExit("No window of a saved forecast has an answer now. Try again later.")
    for year, of_year in tables.items():
        write_tables(of_year, year, config.RESULTS_DIR)
    write_summary(config.RESULTS_DIR)
    print(f"{min(tables)} to {max(tables)}: see results/SUMMARY.md, tables {', '.join(of_year)}.")
