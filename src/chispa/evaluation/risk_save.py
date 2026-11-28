"""Save what a live alert needs for its growth risk: the models and the known outcomes.

`risk_live.py` gives an alert of today its growth risk from one file. This module makes the
file: the six models from each year with an annual map, the values of the alerts that gave the
weights, and the outcomes of the older alerts from the Monitor map as it is now. It gets a new
month of the Monitor map and of the burn days first. `chispa update` runs it when the file is
absent, and one time each day to look for a new month.
`docs/method.md` section 11.35 gives the rules.
"""

from calendar import monthrange
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np

from chispa import confidence, config, risk_files
from chispa.evaluation.confidence import MOMENTS, as_table
from chispa.evaluation.risk import fit_models, key
from chispa.evaluation.risk_inputs import INPUT_SETS
from chispa.evaluation.risk_mark import with_mark
from chispa.evaluation.risk_recalibration import model_facts, percent_rows
from chispa.evaluation.risk_rule import NOW
from chispa.evaluation.risk_run import year_parts
from chispa.evaluation.risk_test import rows_of_month
from chispa.grid import pantanal_grid
from chispa.risk import DIGITS
from chispa.sources import burnday, monitor
from chispa.store import to_text


def map_months(now: datetime, raw_dir: Path) -> dict[int, int]:
    """Return the last month of the saved Monitor map at a time, for this year and the year
    before. A year with no month in the map at that time is not in the answer."""
    found = {}
    for year in (now.year - 1, now.year):
        if monitor.months_on_disk(year, raw_dir):
            came = monitor.read_published(year, raw_dir)
            months = [month for month, time in came.items() if time <= now]
            if months:
                found[year] = max(months)
    return found


def pull_maps(now: datetime, raw_dir: Path, project: str) -> int:
    """Get each new month of the Monitor map and of the burn days, and return how many came."""
    newest = monitor.image_times(project)
    new = 0
    for year in (now.year - 1, now.year):
        has = max((m for m in range(1, 13) if f"brazil-{year}-{m}" in newest), default=0)
        if has > monitor.months_on_disk(year, raw_dir):
            monitor.download_year(year, project, raw_dir, pantanal_grid())
            new += 1
        if has:
            before = len(list((raw_dir / "burnday" / str(year)).glob("*.npz")))
            new += len(burnday.download_year(year, project, raw_dir)) - before
    return new


def weather_until(now: datetime, raw_dir: Path) -> datetime:
    """Return the time to which a row can have its inputs: some days before the end of the
    last complete month of the weather on disk."""
    year, month = now.year, now.month
    for _ in range(24):
        if (raw_dir / "weather" / str(year) / f"{month:02d}.npz").exists():
            last = date(year, month, monthrange(year, month)[1])
            return datetime(last.year, last.month, last.day, tzinfo=UTC) - timedelta(days=5)
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
    raise RuntimeError(f"Run `chispa fetch weather --year {now.year}` first.")


def fit(parts: dict[int, dict], years: list[int]) -> dict[str, dict]:
    """Return the models of the limits of a percentage from the rows of some years, each with
    the values of those rows in sequence: a new value gets its rank from them."""
    training = {
        m: [row for y in years for row in parts[y]["rows"][m] if not row["known"]] for m in MOMENTS
    }
    models = fit_models(training, *INPUT_SETS[NOW], config.RISK_CLASS_LIMITS_HA)
    for moment in MOMENTS:
        for limit in config.RISK_CLASS_LIMITS_HA:
            model = models[key(moment, limit)]
            table = as_table(training[moment], tuple(model["inputs"]))[0]
            values = np.sort(confidence.probability(model, table).round(DIGITS))
            model["reference"] = values.tolist()
    return models


def known_outcomes(parts: dict, models: dict, months: dict[int, int], paths: tuple) -> dict:
    """Return, for each model, the time, the value and the label of each older alert.

    The rows of a year have the outcomes of the Monitor map with its last month at this time,
    as in the replay of section 11.25. Their values come from the models of the years with an
    annual map before that year. The alerts are those that a live alert can be: not near an
    earlier alert, and not with only GOES rows of INPE. `paths` has the store, the raw files
    and the time of now.
    """
    store_path, raw_dir, now = paths
    until = weather_until(now, raw_dir)
    past = {name: {"time": [], "value": [], "large": []} for name in models}
    for year, month in months.items():
        # An alert after the last month of the map has no outcome in it: with a map that is
        # late, such an alert must not count as an alert with no fire.
        map_end = datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=UTC)
        end = min(until, map_end)
        rows = percent_rows(with_mark(rows_of_month(year, month, end, (store_path, raw_dir))))
        earlier = [one for one in parts if one < year]
        of_year = models if earlier == sorted(parts) else fit(parts, earlier)
        for moment in MOMENTS:
            if not rows[moment][0]:
                continue
            for limit in config.RISK_CLASS_LIMITS_HA:
                facts = model_facts({year: rows}, {year: of_year}, moment, limit)[year]
                for name in ("time", "value", "large"):
                    past[key(moment, limit)][name] += facts[name].round(DIGITS).tolist()
    return past


def refresh(store_path: Path, raw_dir: Path, now: datetime, project: str) -> str:
    """Make the file of the live growth risk again if it is absent, of other settings, or if a
    new month of a map came. Return one sentence that says what this did."""
    path = config.RISK_MODELS_PATH
    saved = risk_files.load_models(path)
    new = pull_maps(now, raw_dir, project)
    months = {str(year): month for year, month in map_months(now, raw_dir).items()}
    if saved is not None and not new and saved["map"] == months:
        risk_files.save_models(saved | {"map_checked_at": to_text(now)}, path)
        return "The Monitor map has no new month."
    parts = {year: year_parts(year, store_path, raw_dir) for year in config.YEAR_ROLES}
    models = fit(parts, sorted(parts))
    of_months = {int(year): month for year, month in months.items()}
    past = known_outcomes(parts, models, of_months, (store_path, raw_dir, now))
    times = {"made_at": to_text(now), "map_checked_at": to_text(now)}
    made = times | {"fit_years": sorted(parts), "map": months, "models": models, "past": past}
    risk_files.save_models(made, path)
    return f"New saved models and outcomes: the Monitor map to {months}."
