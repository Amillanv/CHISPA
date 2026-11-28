"""The rows of the test year of the growth risk: a year with no annual map.

The annual map of a year comes in the next year. The Monitor map comes some weeks after each
month. This module makes the fires of the test year from the Monitor map, with the rule of the
annual map, and the rows of its alerts with the inputs of the models. It also makes the replay:
the recalibration of each alert with the map as it was at the time of that alert.
`docs/method.md` section 11.25 gives the rules.
"""

import calendar
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np

from chispa import config, fires
from chispa.evaluation.confidence import MOMENTS, year_rows
from chispa.evaluation.inputs import fire_fields
from chispa.evaluation.match import Fields, match
from chispa.evaluation.risk import seen_first, sized_rows
from chispa.evaluation.risk_inputs import add_model_inputs
from chispa.evaluation.risk_mark import with_mark
from chispa.evaluation.risk_recalibration import (
    answer_table,
    model_facts,
    percent_rows,
    year_level_rows,
)
from chispa.evaluation.run import biome_detections
from chispa.grid import pantanal_grid
from chispa.risk import factors, recalibrate
from chispa.sources import border, burnday, monitor, scars


def monitor_fires(
    year: int, raw_dir: Path, data_dir: Path, last: int | None = None
) -> tuple[np.ndarray, Fields, int]:
    """Return the fire grid and the fires of one year from the Monitor map, and its last month.

    The rule for a fire is that of the annual map (`fires.py`). The step needs some gigabytes
    of memory and some minutes, thus its result is a file, as the fire grid of the annual map.
    With `last`, the map is as it was when that month came: it has no later month, and it has
    the burn days of the months before that month only. The burn day product comes
    approximately one month later than the map (`docs/sources.md` sections 8.9 and 8.18).
    """
    grid = pantanal_grid()
    months, newest = monitor.read_year(year, raw_dir, grid, last)
    name = f"{year}-{last:02d}-replay" if last else f"{year}-{newest:02d}"
    path = data_dir / "fires_monitor" / f"{name}.npz"
    if not path.exists():
        days, coarse = burnday.read_year(year, raw_dir), burnday.burnday_grid()
        if last:
            months[months > last] = 0
            days[last - 1 :] = 0
        rings = border.read_rings(raw_dir / "border" / "pantanal.geojson")
        months *= border.rasterize(rings, grid)
        found, numbers = fires.find_fires(months, scars.find_scars(months), grid, days, coarse)
        fields = fire_fields(found, year)
        del fields["year"]
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, numbers=numbers, **fields)
    saved = np.load(path)
    fields = {name: saved[name] for name in saved.files if name != "numbers"} | {"year": year}
    return saved["numbers"], fields, last or newest


def known_until(year: int, last_month: int) -> datetime:
    """Return the last time of a moment whose outcome the map can have.

    An outcome is known the delay of the recalibration after the moment of its alert, and the
    map ends with the last day of its last month.
    """
    end = date(year, last_month, calendar.monthrange(year, last_month)[1]) + timedelta(days=1)
    start_of_next = datetime(end.year, end.month, end.day, tzinfo=UTC)
    return start_of_next - timedelta(days=config.RISK_RECALIBRATION_DELAY_DAYS)


def _sized(year: int, store_path: Path, raw_dir: Path, last: int | None = None) -> tuple:
    """Return the rows of each moment with sizes from the Monitor map, the detections of the
    year, and the last month of the map."""
    numbers, fields, last = monitor_fires(year, raw_dir, store_path.parent, last)
    detections = biome_detections(year, store_path, raw_dir)
    pairs = match(detections, numbers, pantanal_grid(), fields)
    rows, _ = year_rows(year, store_path, raw_dir, (detections, pairs, fields))
    first, area = seen_first(detections, pairs, fields), fields["area_ha"]
    return {m: sized_rows(rows[m], first, area) for m in MOMENTS}, detections, last


def month_of_test() -> int:
    """Return the last month of the Monitor map in the test: the month whose end is the delay
    of the recalibration after the last moment of a test alert (`config.RISK_TEST_UNTIL`)."""
    end = config.RISK_TEST_UNTIL + timedelta(days=config.RISK_RECALIBRATION_DELAY_DAYS)
    return (end - timedelta(days=1)).month


def _with_inputs(
    sized: dict, detections: Fields, raw_dir: Path, year: int, until: datetime
) -> dict:
    """Return the rows to a time with the inputs of the models, and with no detections.

    The rows have no input of a group that no model has: the sources of some groups do not
    have a year in progress.
    """
    for moment in MOMENTS:
        sized[moment] = [row for row in sized[moment] if row["at"] <= until.timestamp()]
        add_model_inputs(sized[moment], detections, raw_dir, year, until.date() + timedelta(days=5))
        for row in sized[moment]:
            del row["positions"]
    return sized


def monitor_part(year: int, store_path: Path, raw_dir: Path) -> dict:
    """Return the rows of the test year: sizes from the Monitor map, and the inputs of the models.

    Only an alert with a known outcome is in the test.
    """
    # `chispa update` gets each new month of the map. The test reads the map as it was when
    # the month of its first run came: a later month adds no alert, and it changes no outcome.
    sized, detections, last = _sized(year, store_path, raw_dir, month_of_test())
    until = min(known_until(year, last), config.RISK_TEST_UNTIL)
    rows = _with_inputs(sized, detections, raw_dir, year, until)
    return {"rows": rows, "until": until, "states": map_states(year, until, store_path, raw_dir)}


def rows_of_month(year: int, month: int, until: datetime, paths: tuple[Path, Path]) -> dict:
    """Return the rows of one year to a time, with the inputs of the models, and with sizes
    from the Monitor map as it was when one month came. `paths` has the store and the raw files.
    """
    sized, detections, _ = _sized(year, *paths, month)
    return _with_inputs(sized, detections, paths[1], year, until)


def map_states(year: int, until: datetime, store_path: Path, raw_dir: Path) -> list[tuple]:
    """Return each state of the Monitor map in the test year to a time, the oldest first.

    A state has the time from which it applies and, for the year before and for the year, the
    outcome of each alert with the months that the map had at that time. The first state is
    that of the start of the year. A year with no month in the map has no outcome.
    """
    came = sorted(
        (time.timestamp(), one, month)
        for one in (year - 1, year)
        for month, time in monitor.read_published(one, raw_dir).items()
    )
    start, last, states = datetime(year, 1, 1, tzinfo=UTC).timestamp(), {}, []
    for time, one, month in came:
        if time > start and not states:
            states.append((start, dict(last)))
        last[one] = max(last.get(one, 0), month)
        if start < time <= until.timestamp():
            states.append((time, dict(last)))
    outcomes = {}
    for one, month in {pair for _, months in states for pair in months.items()}:
        sized = _sized(one, store_path, raw_dir, month)[0]
        outcomes[(one, month)] = {
            m: {row["alert"]: _outcome(row) for row in sized[m]} for m in MOMENTS
        }
    return [
        (time, {one: outcomes[(one, month)] for one, month in months.items()})
        for time, months in states
    ]


def _outcome(row: dict) -> dict:
    return {name: row[name] for name in ("size_ha", "seen_ha", "known")}


def replay_table(
    parts: dict[int, dict], models: dict[int, dict], year: int, mark: bool = False
) -> list[dict]:
    """Return the answer of the test year with the factor that each alert can have at its time.

    The known outcomes of an alert at the time T come from the state of the map at T, not from
    the map of the end (`docs/method.md` section 11.25). `parts` has the rows of the year before
    and of the test year, with its states. The scored alerts and their outcomes do not change.
    With `mark`, the alerts that are left out are those near an earlier alert, not those that
    the map puts on a known fire: the mark that a live alert has (section 11.35).
    """
    change = with_mark if mark else (lambda rows: rows)
    states, table = parts[year]["states"], []
    scored = {year: percent_rows(change(parts[year]["rows"]))}
    for moment in MOMENTS:
        for limit in config.RISK_CLASS_LIMITS_HA:
            now = model_facts(scored, {year: models[year]}, moment, limit)[year]
            factor = np.ones(len(now["time"]))
            for position, (start, outcomes) in enumerate(states):
                end = states[position + 1][0] if position + 1 < len(states) else np.inf
                chosen = (now["time"] >= start) & (now["time"] < end)
                then = {
                    one: percent_rows(change(_then(parts[one]["rows"], outcomes[one])))
                    for one in outcomes
                }
                older = model_facts(then, {one: models[one] for one in then}, moment, limit)
                past = {
                    name: np.concatenate([one[name] for one in older.values()])
                    for name in ("time", "value", "large")
                }
                factor[chosen] = factors(now["time"][chosen], past)
            row = year_level_rows(now, recalibrate(now["value"], factor), factor)[0]
            table.append({"moment_h": moment, "limit_ha": limit} | row)
    return answer_table(table)


def _then(rows: dict[str, list], outcomes: dict[str, dict]) -> dict[str, list]:
    """Return the rows of a year with the outcome that each alert had in one state of the map."""
    return {m: [row | outcomes[m][row["alert"]] for row in rows[m]] for m in MOMENTS}
