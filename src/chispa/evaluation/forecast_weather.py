"""The weather forecast that we had at a look, for the fronts of a year.

The trees with the weather after the look learn from the recorded weather. A live forecast does
not have that weather: it has a forecast of it. This module gets from Open-Meteo, for each day
with a front, the values that the IFS model predicted 24 hours before each hour, and 48 hours
before for the day after. It makes the inputs of `front_inputs.next_inputs` from them. Thus a
test can score the trees with the weather that we really had at the look.
`docs/method.md` section 11.30 gives the rules.
"""

import hashlib
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np

from chispa import config, fronts
from chispa.evaluation import front_inputs
from chispa.sources import openmeteo, weather

# The blocks and the first day have the forecast of 1 day before. The day after has the forecast
# of 2 days before: its hours are more than 24 hours after the look.
LEADS = (1, 2)
SPAN_DAYS = 3  # A request has the day of the look and the two days after it.


def cells_of(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Return the centre of the cell of the forecast model at each position, as (lat, lon)."""
    step = config.FORECAST_WEATHER_DEG
    return np.column_stack([np.round(lat / step) * step, np.round(lon / step) * step])


def day_file(raw_dir: Path, day: date, cells: np.ndarray) -> Path:
    """Return the raw file of the forecasts for one day and some cells. Get it if it is absent.

    The name has a part of a hash of the cells: a different list of cells is a different file.
    """
    mark = hashlib.sha256(np.round(cells, 2).tobytes()).hexdigest()[:8]
    path = raw_dir / "openmeteo_previous" / str(day.year) / f"{day}_{mark}.json"
    if not path.exists():
        last = day + timedelta(days=SPAN_DAYS - 1)
        openmeteo.download_previous(cells[:, 0], cells[:, 1], (day, last), path)
    return path


def empty_layers(layers: front_inputs.Layers) -> dict[int, front_inputs.Layers]:
    """Return, for each lead, layers with no value: the form of `layers`, some days longer."""
    more = SPAN_DAYS * (24 // weather.BLOCK_HOURS)
    found = {}
    for lead in LEADS:
        days = {
            name: np.full((len(layer) + SPAN_DAYS, *layer.shape[1:]), np.nan, dtype=np.float32)
            for name, layer in layers.days.items()
        }
        shape = (len(layers.wind) + more, *layers.wind.shape[1:]) if lead == LEADS[0] else (0,)
        found[lead] = replace(layers, days=days, wind=np.full(shape, np.nan, dtype=np.float32))
    return found


def forecast_layers(layers: front_inputs.Layers, answers: dict, raw_dir: Path) -> dict:
    """Return, for each lead, layers with the forecast of that lead at the weather cell of each
    front, for the day of its look and the two days after it. The other cells have no value."""
    grid, each = weather.weather_grid(), 24 // weather.BLOCK_HOURS
    rows, cols = grid.rows_cols(answers["lat"], answers["lon"])
    cells = cells_of(answers["lat"], answers["lon"])
    midnight = datetime(*layers.first_day.timetuple()[:3], tzinfo=UTC).timestamp()
    day_of = ((answers["start"] - midnight) // 86400).astype(int)
    found = empty_layers(layers)
    for day in np.unique(day_of):
        part = np.nonzero(day_of == day)[0]
        asked, place = np.unique(cells[part], axis=0, return_inverse=True)
        path = day_file(raw_dir, layers.first_day + timedelta(days=int(day)), asked)
        for lead in LEADS:
            days, wind = openmeteo.read(path, lead)
            for front, at in zip(part, place.ravel(), strict=True):
                for name in days:
                    found[lead].days[name][day : day + SPAN_DAYS, rows[front], cols[front]] = days[
                        name
                    ][at]
                if lead == LEADS[0]:
                    blocks = slice(day * each, (day + SPAN_DAYS) * each)
                    found[lead].wind[blocks, :, rows[front], cols[front]] = wind[at]
    return found


def year_inputs(year: int, answers: dict, raw_dir: Path) -> dict[str, np.ndarray]:
    """Return the inputs of the weather after the look for each front of one year, from the
    forecast that we had at the look. The fronts are in the sequence of their looks."""
    layers = front_inputs.load_layers(raw_dir, year)
    found = forecast_layers(layers, answers, raw_dir)
    first, tomorrow = found[LEADS[0]], found[LEADS[1]].days
    parts = []
    for start in np.unique(answers["start"]):
        part = answers["start"] == start
        centre = fronts.metres(answers["lat"][part], answers["lon"][part])
        parts.append(front_inputs.next_inputs(first, tomorrow, centre, float(start)))
    return {name: np.concatenate([part[name] for part in parts]) for name in parts[0]}
