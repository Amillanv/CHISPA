"""The score of the saved live forecasts against what came.

A live forecast has no answer at its time. Some hours later, the next looks and the GOES masks
of the poller give each front its answer, by the rules of `evaluation/fronts.py`. This module
reads the files of `data/forecasts`, makes each look again as its forecast saw it, and gives
each front of the file its answer. No model has read these fronts: they are a new test.
`docs/method.md` section 11.32 gives the rules.
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from chispa import config, forecast_live, front_inputs, fronts, polls
from chispa.build import live_logs
from chispa.evaluation import burn, forecast
from chispa.evaluation import fronts as steps
from chispa.evaluation.confidence import separation
from chispa.store import read_log_sizes

SIZES = {"3 or more": False, "1 or 2": True}
JOINED = ("seconds", "available", "lat", "lon", "points")
CAME = ("examined", "answer", "new_pixels", "direction_deg", "persistence")


def _hours() -> tuple[int, int]:
    """Return the hours from a look to the start of its first window and to its last end."""
    windows = config.FRONT_WINDOWS_H.values()
    return min(low for low, _ in windows), max(high for _, high in windows)


def check_store(store: sqlite3.Connection, raw_dir: Path) -> None:
    """Stop if a FIRMS log on disk has a row that the store did not read.

    The answers come from the pixels of the store: a pixel that is only in a log is not in them.
    """
    read = read_log_sizes(store)
    for source, path in live_logs(raw_dir):
        name = path.relative_to(raw_dir).as_posix()
        if source == "firms" and read.get(name) != path.stat().st_size:
            raise RuntimeError(f"The store does not have each row of {name}. Run `chispa update`.")


def answered(raw_dir: Path, window: dict, now: datetime) -> bool:
    """Return True if the live data can give the answer of one window of a saved forecast.

    The poller must have a pass that read each source with no failure (`polls.py`) in a span of
    time. The span starts some hours after the end of the window: the hours in which a look must
    be complete (`config.py`), because the pixels of its last pass come late. The span ends one
    read-back of the poller after the start of the window: a later pass does not get the pixels
    and the masks of the window. The time of the clock is not sufficient: after a stop of a
    source, "no pixel" must not become "no new ground".
    """
    first = datetime.fromisoformat(window["to"]) + timedelta(hours=_hours()[0])
    last = min(now, datetime.fromisoformat(window["from"]) + config.LIVE_LOOKBACK)
    at = polls.status(raw_dir, last)["complete_pass_at"] if first <= last else None
    return at is not None and datetime.fromisoformat(at) >= first


def issued(folder: Path, year: int) -> list[dict]:
    """Return, for each look of a year with a file, its forecast as we gave it before the windows.

    That is the newest file of the look that was complete before the first window starts
    (`config.py`). A look with only later files has no forecast of its windows: it is not here.
    The longest window must end in the year of the look, as in the test: the later pixels are
    those of that year.
    """
    first, longest = _hours()
    found = {}
    for path in sorted(folder.glob(f"{year}-*.json")):
        saved = json.loads(path.read_text())
        look_at = datetime.fromisoformat(saved["look_at"])
        in_time = datetime.fromisoformat(saved["made_at"]) < look_at + timedelta(hours=first)
        if in_time and (look_at + timedelta(hours=longest)).year == year:
            found[saved["look_at"]] = saved  # The files are in the sequence of their times.
    return list(found.values())


def as_seen(store: sqlite3.Connection, saved: dict) -> tuple[dict, tuple[int, int]] | None:
    """Return the pixels and the rows of the look of a saved forecast, as the forecast saw them.

    The pixels to the end of the look are those that were available at the time of the file.
    The later pixels are those of the store of now, from the start of the first window.
    None: the look of the store of now is not the look of the file. A pixel of the look came
    after the file, or the store changed. Such a look has no score: the test also counts only a
    look that was complete before its first window (section 11.26).
    """
    start = datetime.fromisoformat(saved["look_at"])
    then = forecast_live.pixels_at(store, start.year, datetime.fromisoformat(saved["pixels_to"]))
    a = 0 if then is None else int(np.searchsorted(then["seconds"], start.timestamp()))
    if then is None or a == len(then["seconds"]):
        return None
    b = int(np.searchsorted(then["look"], then["look"][a], side="right"))
    now = fronts.load_pixels(store, start.year)
    whole = now["look"] == now["look"][np.searchsorted(now["seconds"], then["seconds"][a])]
    if whole.sum() != b - a:
        return None
    later = now["seconds"] >= then["seconds"][a] + _hours()[0] * 3600
    joined = {name: np.concatenate([then[name][:b], now[name][later]]) for name in JOINED}
    return joined, (a, b)


def front_answers(saved: dict, seen: tuple, masks: steps.Masks) -> dict | None:
    """Return the answers of each front of a saved forecast, in the sequence of the file.

    `seen` has the pixels and the rows of the look (`as_seen`). A front of the file is the front
    of the look with the same centre and the same size. None: a front of the file is not in the
    look.
    """
    pixels, (a, b) = seen
    look = fronts.make_look(pixels["points"][a:b], pixels["points"][:a])
    rows = steps.look_rows(pixels, (a, b), look, masks)
    came = front_inputs.came_inputs(look)
    rows["persistence"] = came["log_came"] + came["log_fresh"]
    place = {
        (round(float(lat), 4), round(float(lon), 4), int(size)): number
        for number, (lat, lon, size) in enumerate(
            zip(rows["lat"], rows["lon"], rows["pixels"], strict=True)
        )
    }
    keys = [(front["lat"], front["lon"], front["pixels"]) for front in saved["fronts"]]
    if any(key not in place for key in keys):
        return None
    order = [place[key] for key in keys]
    return {name: values[order] for name, values in rows.items()}


def _came(answers: dict | None, hours: int, number: int) -> dict:
    """Return what came for one front in one window. No answers: each value is absent."""
    if answers is None:
        return dict.fromkeys(CAME)
    direction = answers[f"direction_deg_{hours}"][number]
    return {
        "examined": bool(answers[f"examined_{hours}"][number]),
        "answer": steps.ANSWERS[int(answers[f"answer_{hours}"][number])],
        "new_pixels": int(answers[f"new_{hours}"][number]),
        "direction_deg": None if np.isnan(direction) else round(float(direction), 1),
        "persistence": round(float(answers["persistence"][number]), 4),
    }


def front_table(saved: dict, answers: dict | None, raw_dir: Path, now: datetime) -> list[dict]:
    """Return one row for each front and each window of a saved forecast that has an answer.

    A window has an answer if the live data can give it at the time of now (`answered`). A front
    with no chance has no row. `same_look` is False if the look has no answers (`as_seen`).
    """
    table, has = [], {}
    for number, front in enumerate(saved["fronts"]):
        for hours in config.FRONT_WINDOWS_H:
            window = front.get(f"hours_{hours}")
            if window is None or window["new_ground"] is None:
                continue
            if hours not in has:  # The fronts of one file have the same windows.
                has[hours] = answered(raw_dir, window, now)
            if not has[hours]:
                continue
            guess = forecast.directions(np.array(list(window["sectors"].values()))[None])[0]
            row = {name: saved[name] for name in ("look_at", "made_at")}
            row |= {"trees": saved.get("trees"), "hours": hours}
            row |= {name: front[name] for name in ("lat", "lon", "pixels")}
            row |= {"new_ground": window["new_ground"], "large_growth": window["large_growth"]}
            row["forecast_direction_deg"] = round(float(guess), 1)
            row["same_look"] = answers is not None
            table.append(row | _came(answers, hours, number))
    return table


def summary(table: list[dict]) -> list[dict]:
    """Return the scores of the saved forecasts for each window and each size of front.

    A front has a score if its look is the look of the file and GOES examined its place, as in
    the test of section 11.31. `chance_sum` is the number of fronts with new ground that the
    stated chances expect.
    """
    found = []
    for hours in config.FRONT_WINDOWS_H:
        for size, small in SIZES.items():
            limit = config.FRONT_SMALL_BELOW
            of = [r for r in table if r["hours"] == hours and (r["pixels"] < limit) == small]
            scored = [row for row in of if row["examined"]]
            came = np.array([row["new_pixels"] > 0 for row in scored], dtype=float)
            chance = np.array([row["new_ground"] for row in scored])
            many = [row for row in scored if row["new_pixels"] >= config.FRONT_DIRECTION_PIXELS]
            guess = np.array([row["forecast_direction_deg"] for row in many])
            truth = np.array([row["direction_deg"] for row in many], dtype=float)
            both = 0 < came.sum() < len(came)
            persistence = np.array([row["persistence"] for row in scored])
            row = {"hours": hours, "size": size, "looks": len({r["look_at"] for r in of})}
            row |= {"fronts": len(of), "same_look": sum(r["same_look"] for r in of)}
            row |= {"examined": len(scored), "new_ground": int(came.sum())}
            row["chance_sum"] = round(float(chance.sum()), 1)
            row["auc_trees"] = separation(chance, came) if both else None
            row["auc_persistence"] = separation(persistence, came) if both else None
            row["fronts_with_direction"] = len(many)
            # A small front has no direction in an alert: its sectors are in the file only.
            row["trees_in_45"] = forecast.in_45(guess, truth, np.ones(len(many), dtype=bool))
            found.append(row)
    return found


def score_tables(store_path: Path, raw_dir: Path, now: datetime) -> dict[int, dict[str, list]]:
    """Return the table `forecast_live` of each year with a saved forecast that has an answer.

    This also saves one row for each front and each window in a file of the results of the
    year. The masks are those of the live poller: each scan that it recorded.
    """
    store, folder, tables = sqlite3.connect(store_path), config.FORECAST_LIVE_DIR, {}
    check_store(store, raw_dir)
    masks = steps.masks_in(raw_dir / "live")
    for year in sorted({int(path.name[:4]) for path in folder.glob("*.json")}):
        table = []
        for saved in issued(folder, year):
            seen = as_seen(store, saved)
            answers = front_answers(saved, seen, masks) if seen else None
            table += front_table(saved, answers, raw_dir, now)
        if table:
            burn.write(config.RESULTS_DIR / str(year) / "forecast_live" / "fronts.csv", table)
            tables[year] = {"forecast_live": summary(table)}
    return tables
