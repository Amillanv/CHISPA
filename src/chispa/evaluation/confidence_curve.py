"""The confidence model against the burn curve: a test that needs no map of burn scars.

The model of `confidence.py` learned the match with the map, which comes in the next year.
The burn curve gives an outcome some weeks after an event. This module asks the same question
as the confidence check with that outcome: does the model put the alerts in a better sequence
than the level? `docs/method.md` section 11.18 gives the rules.
"""

import sqlite3
from pathlib import Path

import numpy as np

from chispa import confidence, config, severity
from chispa.evaluation.confidence import (
    MOMENTS,
    as_table,
    detection_fires,
    event_fires,
    moment_rows,
    separation,
    top_tenth,
)
from chispa.evaluation.moments import load_merges
from chispa.evaluation.run import biome_detections, prepare


def curve_table(rows: dict[str, list], models: dict[str, dict], outcome_of: tuple) -> list[dict]:
    """Return the model against the level, with the burn curve as the outcome of an alert.

    `outcome_of` has the answer of the curve at its last day for each event of the end of the
    year, and True if the year has a map of burn scars.
    An alert has the answer of the event that holds it. With no answer, it is not in the table.
    The match values are for the same alerts. A year with no map has no value for them.
    """
    burned, has_map = outcome_of
    table = []
    for moment in MOMENTS:
        model = models[moment]
        own = [row for row in rows[moment] if burned.get(row["event"]) is not None]
        inputs, matched = as_table(own, tuple(model["inputs"]))
        outcome = np.array([burned[row["event"]] for row in own], dtype=float)
        values = {
            "probability": confidence.probability(model, inputs),
            "level": np.array([row["level"] for row in own], dtype=float),
        }
        for name, value in values.items():
            top = top_tenth(value)
            table.append(
                {
                    "moment_h": moment,
                    "measure": name,
                    "alerts": len(own),
                    "alerts_burned": int(outcome.sum()),
                    "burn_separation": separation(value, outcome),
                    "top_tenth": len(top),
                    "top_tenth_burned": int(outcome[top].sum()),
                    "alerts_matched": int(matched.sum()) if has_map else None,
                    "match_separation": separation(value, matched) if has_map else None,
                }
            )
    return table


def curve_tables(year: int, store_path: Path, raw_dir: Path, burned: dict) -> dict[str, list[dict]]:
    """Return the table of the confidence against the burn curve for one fused year.

    A year with a map of burn scars has the match of each alert also. A year with no map has
    the detections only: an alert has no fire there.
    """
    if year in config.YEAR_ROLES:
        detections, pairs, fires, _ = prepare(year, store_path, raw_dir)
        links = (event_fires(detections, pairs, fires), detection_fires(detections, pairs, fires))
    else:
        detections = biome_detections(year, store_path, raw_dir)
        nothing = np.zeros(len(detections["event"]) + 1, dtype=int), np.array([], dtype=int)
        links = ({}, nothing)
    layers = severity.load_layers(raw_dir, severity.cover_year(year))
    merges = load_merges(sqlite3.connect(store_path), year)
    rows = moment_rows(detections, merges, links, layers)
    path = config.RESULTS_DIR / str(config.DEVELOPMENT_YEAR) / "confidence" / "model.json"
    outcome_of = (burned, year in config.YEAR_ROLES)
    return {"confidence_curve": curve_table(rows, confidence.load(path), outcome_of)}
