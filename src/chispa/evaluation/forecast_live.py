"""A growth forecast for the fronts that burn now, from the trees of the development years.

The evaluation scores the forecast on recorded years. This module makes the forecast of the
newest looks: the same fronts, the same inputs and the same trees, with no answer yet.
ERA5-Land is some days late, thus the weather of the newest days comes from Open-Meteo.
The forecast of each look is one JSON object, saved in a file with the time when we made it.
A later run can score those files against what came: they are data that no model has read.
`docs/method.md` section 11.29 gives the rules.
"""

import hashlib
import json
import pickle
import sqlite3
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import sklearn

from chispa import config, fronts
from chispa.evaluation import forecast, forecast_run, front_inputs
from chispa.evaluation import fronts as steps
from chispa.evaluation.report import config_hash
from chispa.grid import pantanal_grid
from chispa.sources import border, openmeteo, weather
from chispa.store import to_text

SECTORS = ("north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west")
EVENTS = """
SELECT d.lat, d.lon, m.event_id FROM detections d JOIN memberships m ON m.detection_id = d.id
WHERE d.sensor_family = ? AND d.source = ? AND d.observed_at >= ? AND d.observed_at <= ?
"""
# One row that changes when a detection of the development years changes in the store.
TRAINING = """
SELECT COUNT(*), TOTAL(lat), TOTAL(lon), TOTAL(frp_mw), MAX(available_at) FROM detections
WHERE sensor_family = ? AND source = ? AND observed_at >= ? AND observed_at < ?
"""
NO_INPUTS = "no weather before the look, or no pixel with a fire power"


def _stamp(store_path: Path) -> str:
    """Return a mark of what makes the trees: the configuration, the code of the rows and of the
    trees, the version of scikit-learn, and the detections of the development years in the store.

    A raw file does not change (`docs/sources.md` section 8.7), thus the mark does not read the
    raw layers. After a new download of a layer of a development year, delete the saved file.
    """
    modules = (fronts, steps, front_inputs, forecast, forecast_run)
    code = "".join(Path(module.__file__).read_text() for module in modules)
    years = (f"{min(config.FRONT_YEARS)}-01-01", f"{max(config.FRONT_YEARS) + 1}-01-01")
    store = sqlite3.connect(store_path)
    data = store.execute(TRAINING, (fronts.SENSOR_FAMILY, steps.SOURCE, *years)).fetchone()
    made_from = f"{code}{sklearn.__version__}{data}"
    return config_hash() + hashlib.sha256(made_from.encode()).hexdigest()[:12]


def saved_models(store_path: Path, raw_dir: Path, in_biome: np.ndarray) -> dict:
    """Return the trees of each question and their input names, from all development years.

    A saved file gives them, if the configuration, the code and the detections that made it
    are those of now. If not, this fits the trees again and saves them: some minutes.
    """
    path, stamp = config.FORECAST_MODELS_PATH, _stamp(store_path)
    if path.exists():
        saved = pickle.loads(path.read_bytes())
        if saved["config"] == stamp:
            return saved
    years = config.FRONT_YEARS
    cases = forecast_run.year_cases(
        {year: forecast.year_rows(year, store_path, raw_dir, in_biome) for year in years}
    )
    saved = {"config": stamp, "models": {}, "names": {}}
    for key, case in cases[years[0]].items():
        train = forecast_run.training(cases, years, key)
        saved["models"][key] = forecast.fit_trees(train["x"], train["y"], train["years"])
        saved["names"][key] = case["names"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pickle.dumps(saved))
    return saved


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


def newest_fronts(pixels: dict, in_biome: np.ndarray, since: float) -> list[dict]:
    """Return the looks that started at or after the time `since` and have a front that counts."""
    found = []
    for a, b, look in steps.each_look(pixels):
        if pixels["seconds"][a] < since:
            continue
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
    each sector. A front with no inputs has no chance: the trees have no score for such a front.
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
            one |= dict.fromkeys((f"hours_{hours}" for hours in windows), None)
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
    """Return the events of the pixels of each front of a look that counts, from the store of now.

    An alert is for an event, and a front has no event. This list joins a front to its alerts.
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


def live_looks(store_path: Path, raw_dir: Path, now: datetime) -> list[dict]:
    """Return one object for each of the newest looks with a front: the time of the look, the
    time of now, and the forecast of each front. No front: an empty list."""
    grid = pantanal_grid()
    in_biome = border.rasterize(border.read_rings(raw_dir / "border" / "pantanal.geojson"), grid)
    store = sqlite3.connect(store_path)
    pixels = steps.load_pixels(store, now.year)
    since = (now - timedelta(hours=config.FORECAST_LIVE_HOURS)).timestamp()
    looks = newest_fronts(pixels, in_biome, since)
    if not looks:
        return []
    saved = saved_models(store_path, raw_dir, in_biome)
    centres = np.concatenate(
        [
            np.column_stack([one["places"]["lat"][one["keep"]], one["places"]["lon"][one["keep"]]])
            for one in looks
        ]
    )
    last = datetime.fromtimestamp(float(pixels["seconds"][looks[-1]["bounds"][1] - 1]), UTC).date()
    layers = live_layers(raw_dir, centres, last)
    found = []
    for one in looks:
        keep = one["keep"]
        inputs = front_inputs.look_inputs(pixels, one["bounds"], one["look"], layers)
        places = {name: values[keep] for name, values in one["places"].items()}
        kept = {name: values[keep] for name, values in inputs.items()}
        look_at = datetime.fromtimestamp(float(places["start"][0]), UTC)
        times = {"look_at": look_at.isoformat(timespec="minutes")}
        times["made_at"] = now.isoformat(timespec="minutes")
        rows = front_rows(saved, places, kept, open_windows(look_at, now))
        for front, events in zip(rows, front_events(store, pixels, one), strict=True):
            front["events"] = events
        found.append(times | {"fronts": rows})
    return found


def save(looks: list[dict], folder: Path) -> list[Path]:
    """Save the forecast of each look as a new file, and return the new files.

    The name of a file has the time of the look and the time of the run, and a file never
    changes: the first forecast of a look stays as we gave it. A look gets a newer file only
    when it has more pixels than in its newest file: a second satellite came.
    """
    written = []
    for look in looks:
        name = look["look_at"][:16].replace(":", "")
        before = sorted(folder.glob(f"{name}_*.json"))
        pixels = sum(front["pixels"] for front in look["fronts"])
        if before:
            newest = json.loads(before[-1].read_text())["fronts"]
            if sum(front["pixels"] for front in newest) >= pixels:
                continue
        path = folder / f"{name}_{look['made_at'][:16].replace(':', '')}.json"
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(look, indent=1))
            written.append(path)
    return written
