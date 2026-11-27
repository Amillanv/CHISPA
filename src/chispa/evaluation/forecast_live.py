"""A growth forecast for the fronts that burn now, from the trees of the development years.

The evaluation scores the forecast on recorded years. This module makes the forecast of the
newest looks: the same fronts, the same inputs and the same trees, with no answer yet.
ERA5-Land is some days late, thus the weather of the newest days comes from Open-Meteo.
The forecast of each look is one JSON object. `forecast_files.py` saves it in a file with the
time when we made it, and the event record reads that file.
A later run can score those files against what came: they are data that no model has read.
`docs/method.md` section 11.29 gives the rules.
"""

import sqlite3
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np

from chispa import config, forecast_files, fronts
from chispa.evaluation import forecast, forecast_trees, front_inputs
from chispa.evaluation import fronts as steps
from chispa.grid import pantanal_grid
from chispa.sources import border, openmeteo, weather
from chispa.store import to_text

SECTORS = ("north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west")
EVENTS = """
SELECT d.lat, d.lon, m.issued_id FROM detections d JOIN memberships m ON m.detection_id = d.id
WHERE d.sensor_family = ? AND d.source = ? AND d.observed_at >= ? AND d.observed_at <= ?
"""
NO_INPUTS = "no weather before the look, or no pixel with a fire power"
ANY_PIXEL = """
SELECT 1 FROM detections WHERE sensor_family = ? AND source = ? AND observed_at >= ?
AND observed_at < ? AND available_at <= ? LIMIT 1
"""


def _biome(raw_dir: Path) -> np.ndarray:
    rings = border.read_rings(raw_dir / "border" / "pantanal.geojson")
    return border.rasterize(rings, pantanal_grid())


def newest_days(layers: front_inputs.Layers, cells: np.ndarray, path: Path) -> front_inputs.Layers:
    """Return the layers with the days of a saved Open-Meteo answer after their last day.

    `cells` has the row and the column of each position of the answer. The other cells of the
    new days have no value.
    """
    days, wind = openmeteo.read(path)
    more = {
        name: np.full((days[name].shape[1], *layer.shape[1:]), np.nan, dtype=layer.dtype)
        for name, layer in layers.days.items()
    }
    blocks = np.full((wind.shape[1], *layers.wind.shape[1:]), np.nan, dtype=layers.wind.dtype)
    for place, (row, col) in enumerate(cells):
        for name in more:
            more[name][:, row, col] = days[name][place]
        blocks[:, :, row, col] = wind[place]
    joined = {name: np.concatenate([layers.days[name], more[name]]) for name in more}
    return replace(layers, days=joined, wind=np.concatenate([layers.wind, blocks]))


def live_layers(raw_dir: Path, centres: np.ndarray, last: date) -> front_inputs.Layers:
    """Return the layers for the fronts with these centres, with the weather to the day `last`.

    The days after the last day of ERA5-Land on disk come from Open-Meteo, for the weather cells
    of the centres.
    """
    layers = front_inputs.load_layers(raw_dir, last.year)
    first = layers.first_day + timedelta(days=len(layers.days["rain_mm"]))
    if first > last:
        return layers
    grid = weather.weather_grid()
    cells = np.unique(np.column_stack(grid.rows_cols(centres[:, 0], centres[:, 1])), axis=0)
    lats, lons = grid.lats()[cells[:, 0]], grid.lons()[cells[:, 1]]
    return newest_days(layers, cells, openmeteo.download(lats, lons, (first, last), raw_dir))


def pixels_at(store: sqlite3.Connection, year: int, now: datetime) -> dict | None:
    """Return the VIIRS pixels of one year that were available at the time of now.

    None: we had no pixel of that year. On 1 January that is the usual state of the new year.
    """
    span = (fronts.SENSOR_FAMILY, steps.SOURCE, f"{year}-01-01", f"{year + 1}-01-01", to_text(now))
    if store.execute(ANY_PIXEL, span).fetchone() is None:
        return None
    pixels = steps.load_pixels(store, year)
    had = pixels["available"] <= now.timestamp()
    pixels = {name: values[had] for name, values in pixels.items()}
    # A look is a group of the pixels that we had: make the groups again.
    return pixels | {"look": fronts.looks(pixels["seconds"])}


def newest_fronts(pixels: dict, in_biome: np.ndarray, since: float) -> list[dict]:
    """Return the looks that started at or after the time `since` and have a front that counts."""
    found = []
    for a, b, look in steps.each_look(pixels, since):
        places = steps.places(pixels, (a, b), look)
        keep = steps.counted(places, in_biome)
        if keep.any():
            found.append({"bounds": (a, b), "look": look, "places": places, "keep": keep})
    return found


def open_windows(look_at: datetime, now: datetime) -> dict[int, dict[str, str]]:
    """Return the limits of each window of a look that has not ended at the time of now.

    A window is from and to some hours after the start of the look (`config.py`). A window that
    ended is in the past: it gets no forecast.
    """
    found = {}
    for hours, (low, high) in config.FRONT_WINDOWS_H.items():
        if look_at + timedelta(hours=high) > now:
            limits = {"from": look_at + timedelta(hours=low), "to": look_at + timedelta(hours=high)}
            found[hours] = {name: at.isoformat(timespec="minutes") for name, at in limits.items()}
    return found


def front_rows(saved: dict, places: dict, inputs: dict, windows: dict) -> list[dict]:
    """Return one object for each front: its place, its size, and its chances for each window.

    A window has its limits, and the chance of new ground, of large growth, and of a new pixel in
    each sector. A front with no inputs has its windows with no chance, and the reason: the trees
    have no score for such a front.
    """
    chance, usable = {}, forecast.has_inputs(inputs)
    for key, model in saved["models"].items():
        table, names = forecast.matrix(inputs, key[0] == "sector")
        if names != saved["names"][key]:
            path = config.FORECAST_MODELS_PATH
            raise RuntimeError(f"Delete {path}: its inputs are not the inputs of now.")
        chance[key] = model.predict_proba(table)[:, 1]
    found = []
    for front in range(len(places["pixels"])):
        one = {name: round(float(places[name][front]), 4) for name in ("lat", "lon")}
        one["pixels"] = int(places["pixels"][front])
        if not usable[front]:
            nothing = dict.fromkeys(("new_ground", "large_growth", "sectors"))
            one |= {f"hours_{hours}": limits | nothing for hours, limits in windows.items()}
            found.append(one | {"no_forecast": NO_INPUTS})
            continue
        for hours, limits in windows.items():
            sectors = chance[("sector", hours)].reshape(-1, config.FRONT_SECTORS)[front]
            one[f"hours_{hours}"] = limits | {
                "new_ground": round(float(chance[("new_ground", hours)][front]), 4),
                "large_growth": round(float(chance[("large_growth", hours)][front]), 4),
                "sectors": {
                    name: round(float(value), 4)
                    for name, value in zip(SECTORS, sectors, strict=True)
                },
            }
        found.append(one)
    return found


def front_events(store: sqlite3.Connection, pixels: dict, one: dict) -> list[list[int]]:
    """Return, for each front of a look that counts, the ids of the events of its pixels as we
    issued them.

    An alert is for an event, and a front has no event. This list joins a front to its alerts.
    An issued id does not change when two events merge: thus the list is correct at a later time.
    """
    a, b = one["bounds"]
    span = [
        to_text(datetime.fromtimestamp(float(pixels["seconds"][row]), UTC)) for row in (a, b - 1)
    ]
    rows = store.execute(EVENTS, (fronts.SENSOR_FAMILY, steps.SOURCE, *span)).fetchall()
    events = {int(front): set() for front in np.nonzero(one["keep"])[0]}
    if rows:
        lat, lon, ids = (np.array(column) for column in zip(*rows, strict=True))
        distance, nearest = one["look"].tree.query(fronts.metres(lat, lon))
        labels = one["look"].labels[nearest]
        for label, event in zip(labels[distance < 1.0], ids[distance < 1.0], strict=True):
            if int(label) in events:
                events[int(label)].add(int(event))
    return [sorted(found) for found in events.values()]


def look_forecast(
    one: dict, pixels: dict, layers: front_inputs.Layers, saved: dict, now: datetime
) -> dict:
    """Return the object of one look: its time, the time to which it has pixels, and the forecast
    of each front. The object has the minimum of a large growth: a later reader needs the value
    of the day of the forecast."""
    keep = one["keep"]
    inputs = front_inputs.look_inputs(pixels, one["bounds"], one["look"], layers)
    places = {name: values[keep] for name, values in one["places"].items()}
    kept = {name: values[keep] for name, values in inputs.items()}
    look_at = _look_at(one)
    times = {"look_at": look_at.isoformat(timespec="minutes"), "pixels_to": to_text(now)}
    times["large_growth_pixels"] = config.FRONT_LARGE_PIXELS
    return times | {"fronts": front_rows(saved, places, kept, open_windows(look_at, now))}


def _look_at(one: dict) -> datetime:
    return datetime.fromtimestamp(float(one["places"]["start"][0]), UTC)


def _is_new(one: dict, folder: Path) -> bool:
    pixels = int(one["places"]["pixels"][one["keep"]].sum())
    return forecast_files.is_new(folder, _look_at(one).isoformat(timespec="minutes"), pixels)


def recent_looks(store: sqlite3.Connection, raw_dir: Path, now: datetime) -> list[tuple]:
    """Return (pixels of its year, look) for each look of the last hours with a front that counts.

    The last hours can have looks of two years: on 1 January, a look of 31 December is in them.
    A look has the known pixels of its year only, as in the test (section 11.26, rule 4).
    """
    since = now - timedelta(hours=config.FORECAST_LIVE_HOURS)
    found, in_biome = [], None
    for year in range(since.year, now.year + 1):
        pixels = pixels_at(store, year, now)
        # No new pixel: an update gets its answer quickly, with no read of the border.
        if pixels is None or not (pixels["seconds"] >= since.timestamp()).any():
            continue
        in_biome = _biome(raw_dir) if in_biome is None else in_biome
        found += [(pixels, one) for one in newest_fronts(pixels, in_biome, since.timestamp())]
    return found


def _year_layers(raw_dir: Path, looks: list[tuple]) -> front_inputs.Layers:
    """Return the layers for the looks of one year, with the weather to the day of the last."""
    places = [
        (one["places"]["lat"][one["keep"]], one["places"]["lon"][one["keep"]]) for _, one in looks
    ]
    centres = np.concatenate([np.column_stack(place) for place in places])
    pixels, newest = looks[-1]
    last = datetime.fromtimestamp(float(pixels["seconds"][newest["bounds"][1] - 1]), UTC).date()
    return live_layers(raw_dir, centres, last)


def live_looks(
    store_path: Path, raw_dir: Path, now: datetime, only_new: Path | None = None
) -> list[dict] | None:
    """Return one object for each of the newest looks with a front: the time of the look, the
    time of now, and the forecast of each front. No front: an empty list.

    `only_new` is the folder of the forecast files, for the step of `chispa update`. Then the
    answer has only the looks that are new in that folder, and this does not fit the trees:
    the answer is None if the saved trees are not those of now.
    """
    store = sqlite3.connect(store_path)
    looks = recent_looks(store, raw_dir, now)
    if only_new:
        looks = [(pixels, one) for pixels, one in looks if _is_new(one, only_new)]
    if not looks:
        return []
    trees = forecast_trees.current if only_new else forecast_trees.fitted
    saved = trees(store_path) if only_new else trees(store_path, raw_dir)
    if saved is None:
        return None
    found = []
    for year in sorted({_look_at(one).year for _, one in looks}):
        of_year = [(pixels, one) for pixels, one in looks if _look_at(one).year == year]
        layers = _year_layers(raw_dir, of_year)
        for pixels, one in of_year:
            made = look_forecast(one, pixels, layers, saved, now)
            for front, events in zip(made["fronts"], front_events(store, pixels, one), strict=True):
                front["events"] = events
            found.append(made)
    return found
