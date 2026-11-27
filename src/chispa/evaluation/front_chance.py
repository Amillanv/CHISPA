"""For an alert that only GOES started: the chance that its event gets a front.

The growth forecast is for a front of VIIRS pixels (`fronts.py`). An alert that only GOES
started has no front, thus it has no forecast. This module asks if we can say at the alert how
probable a front is at the second moment of the growth risk, 24 hours after the first detection.
A logistic regression gets the inputs of the growth risk at the first moment, without the ground
that burned before. Each year gets the model of the other development years.
`docs/method.md` section 11.34 gives the rules.
"""

import sqlite3
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np

from chispa import confidence, config
from chispa.evaluation import front_alerts
from chispa.evaluation.confidence import names_of, separation, year_rows
from chispa.evaluation.forecast_say import chance_rows
from chispa.evaluation.report import share
from chispa.evaluation.risk import weight_table
from chispa.evaluation.risk_inputs import FIRST_HOURS, REMOVED, WEATHER_LATE, add_model_inputs
from chispa.evaluation.run import biome_detections

MOMENT = "0"  # The first moment of the growth risk: one pass gap after the first detection.
NAMES = tuple(name for name in names_of(MOMENT) if name not in REMOVED)
NAMES += FIRST_HOURS + WEATHER_LATE
# A year needs no mapped fire for this: the rows get no fire.
NO_FIRES = ((np.empty(0, dtype=int), np.empty(0, dtype=int)), {"counted": np.empty(0, dtype=bool)})
TABLES = ("front_chance", "front_chance_bands", "front_chance_weights")
# The inputs of a baseline with only the hour of the first detection: how near a VIIRS pass is.
HOUR = ("hour_sin", "hour_cos")


def weather_last(raw_dir: Path, year: int) -> date:
    """Return the last day of the weather for the rows of a year.

    It is 10 January of the next year, as in the growth risk. For a year in progress it is the
    last day of the last complete month on disk.
    """
    last = date(year + 1, 1, 10)
    for _ in range(13):
        if (raw_dir / "weather" / str(last.year) / f"{last.month:02d}.npz").exists():
            return last
        last = date(last.year, last.month, 1) - timedelta(days=1)
    raise RuntimeError(f"Run `chispa fetch weather --year {year}` first.")


def goes_alerts(year: int, store_path: Path, raw_dir: Path) -> list[dict]:
    """Return one row for each alert of a year in the biome that had only GOES detections at
    the first moment, with its inputs.

    The second moment of an alert must be in the year, and before the end of a year in progress
    (`config.py`): the later pixels are those of that year. Its day must have its weather.
    """
    detections = biome_detections(year, store_path, raw_dir)
    rows = year_rows(year, store_path, raw_dir, (detections, *NO_FIRES))[0][MOMENT]
    last = weather_last(raw_dir, year)
    end = datetime(year + 1, 1, 1, tzinfo=UTC).timestamp()
    end = min(end, config.FRONT_TEST_END.timestamp()) - config.SEVERITY_EVAL_HOURS * 3600
    kept = []
    for row in rows:
        only_goes = (detections["family"][row["positions"]] == "abi").all()
        in_time = datetime.fromtimestamp(row["at"], UTC).date() <= last and row["at"] < end
        if only_goes and in_time:
            kept.append(row)
    add_model_inputs(kept, detections, raw_dir, year, last)
    for row in kept:
        del row["positions"]
    return kept


def with_fronts(rows: list[dict], store_path: Path, year: int) -> list[dict]:
    """Return the rows with `front`: True if the event of the alert had a front at the second
    moment.

    The second moment is some hours after the first detection (`config.py`). The event has a
    front if it has a VIIRS pixel of FIRMS that was available then (`front_alerts.py`).
    """
    pixels, merges = front_alerts.load(sqlite3.connect(store_path), year)
    gap = config.PASS_GAP.total_seconds()
    alerts = [(row["alert"], row["at"] - gap) for row in rows]
    column = config.FRONT_ALERT_DELAYS_H.index(config.SEVERITY_EVAL_HOURS)
    sizes = front_alerts.front_sizes(alerts, pixels, merges)[:, column]
    return [row | {"front": bool(size > 0)} for row, size in zip(rows, sizes, strict=True)]


def _table(rows: list[dict], names: tuple[str, ...]) -> np.ndarray:
    return np.array([[row["inputs"][name] for name in names] for row in rows])


def year_tables(rows: list[dict], training: list[dict], baseline: dict) -> dict[str, list]:
    """Return the tables of one year, from the model of the rows of the training years.

    `baseline` is the model of the confidence at the first moment: the probability that an
    alert is a mapped fire. `auc_hour` is for a regression with only the hour of the first
    detection, from the same training rows. The Brier skill score compares the chance with one
    number, the share of the training rows with a front: more than 0 is better than that number.
    """
    label = np.array([row["front"] for row in rows], dtype=float)
    had = np.array([row["front"] for row in training], dtype=float)
    model = confidence.fit(_table(training, NAMES), had, NAMES)
    chance = confidence.probability(model, _table(rows, NAMES))
    known = confidence.probability(baseline, _table(rows, tuple(baseline["inputs"])))
    alone, brier = np.mean((had.mean() - label) ** 2), np.mean((chance - label) ** 2)
    row = {"alerts": len(label), "with_front": int(label.sum())}
    row |= {"share": share(label.sum(), len(label)), "training_share": round(had.mean(), 4)}
    row |= {"expected": round(float(chance.sum()), 1), "auc_model": separation(chance, label)}
    row["auc_confidence"] = separation(known, label)
    row["auc_detections"] = separation(_table(rows, ("detections_log",))[:, 0], label)
    clock = confidence.fit(_table(training, HOUR), had, HOUR)
    row["auc_hour"] = separation(confidence.probability(clock, _table(rows, HOUR)), label)
    row["brier_skill"] = round(float(1 - brier / alone), 4) if alone else None
    bands = chance_rows(("front", int(config.SEVERITY_EVAL_HOURS)), chance, label)
    return dict(zip(TABLES, ([row], bands, weight_table({"front": model})), strict=True))


def chance_tables(store_path: Path, raw_dir: Path, test_run: bool) -> dict[int, dict]:
    """Return the tables of each development year, and of each test year in a test run."""
    years = config.FRONT_YEARS + (config.FRONT_TEST_YEARS if test_run else ())
    parts = {
        year: with_fronts(goes_alerts(year, store_path, raw_dir), store_path, year)
        for year in years
    }
    for year, rows in parts.items():
        if not rows:
            raise RuntimeError(f"The store has no alert of {year} that only GOES started.")
    path = config.RESULTS_DIR / str(config.DEVELOPMENT_YEAR) / "confidence" / "model.json"
    baseline, tables = confidence.load(path)[MOMENT], {}
    for year in years:
        others = [other for other in config.FRONT_YEARS if other != year]
        training = [row for other in others for row in parts[other]]
        tables[year] = year_tables(parts[year], training, baseline)
    return tables
