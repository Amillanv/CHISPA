"""A growth forecast for the fronts that burn now, from the trees of the development years.

The evaluation scores the forecast on recorded years. This module makes the forecast of the
newest looks: the same fronts, the same inputs and the same trees, with no answer yet.
ERA5-Land is some days late, thus the weather of the newest days comes from Open-Meteo.
Each look gets a file with its forecast and the time when we made it. A later run can score
those files against what came: they are data that no model has read.
`docs/method.md` section 11.29 gives the rules.
"""

import csv
import pickle
import sqlite3
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from chispa import config
from chispa.evaluation import forecast, forecast_run, front_inputs
from chispa.evaluation import fronts as steps
from chispa.evaluation.report import config_hash
from chispa.grid import pantanal_grid
from chispa.sources import border, openmeteo, weather

SECTORS = ("north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west")
SHOWN_SECTORS = 3  # A text names this many most likely sectors (`evaluation/forecast_say.py`).


def saved_models(store_path: Path, raw_dir: Path, in_biome: np.ndarray) -> dict:
    """Return the trees of each question and their input names, from all development years.

    A saved file gives them, if the configuration that made it is the configuration of now.
    If not, this fits the trees again and saves them: some minutes.
    """
    path, stamp = config.FORECAST_MODELS_PATH, config_hash()
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


def front_rows(saved: dict, places: dict, inputs: dict, made_at: datetime) -> list[dict]:
    """Return one row for each front: its place, its size, and the chance of each question."""
    chance = {}
    for key, model in saved["models"].items():
        table, names = forecast.matrix(inputs, key[0] == "sector")
        if names != saved["names"][key]:
            path = config.FORECAST_MODELS_PATH
            raise RuntimeError(f"Delete {path}: its inputs are not the inputs of now.")
        chance[key] = model.predict_proba(table)[:, 1]
    rows = []
    for front in range(len(places["pixels"])):
        look_at = datetime.fromtimestamp(float(places["start"][front]), UTC)
        row = {"look_at": look_at.isoformat(timespec="minutes")}
        row |= {"made_at": made_at.isoformat(timespec="minutes")}
        row |= {name: round(float(places[name][front]), 4) for name in ("lat", "lon")}
        row["pixels"] = int(places["pixels"][front])
        for hours in config.FRONT_WINDOWS_H:
            for question in ("new_ground", "large_growth"):
                row[f"{question}_{hours}"] = round(float(chance[(question, hours)][front]), 4)
            sectors = chance[("sector", hours)].reshape(-1, config.FRONT_SECTORS)[front]
            row |= {
                f"{name}_{hours}": round(float(value), 4)
                for name, value in zip(SECTORS, sectors, strict=True)
            }
        rows.append(row)
    return rows


def live_rows(store_path: Path, raw_dir: Path, now: datetime) -> list[dict]:
    """Return the forecast of each front of the newest looks. No front: an empty list."""
    grid = pantanal_grid()
    in_biome = border.rasterize(border.read_rings(raw_dir / "border" / "pantanal.geojson"), grid)
    pixels = steps.load_pixels(sqlite3.connect(store_path), now.year)
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
    rows = []
    for one in looks:
        keep = one["keep"]
        inputs = front_inputs.look_inputs(pixels, one["bounds"], one["look"], layers)
        places = {name: values[keep] for name, values in one["places"].items()}
        kept = {name: values[keep] for name, values in inputs.items()}
        rows += front_rows(saved, places, kept, now)
    return rows


def save(rows: list[dict], folder: Path) -> list[Path]:
    """Save the forecast of each look in its file, and return the files that are new or changed.

    A look can get more pixels when a second satellite comes. Then its fronts have more pixels,
    and the newer forecast replaces the file. If not, the file stays as we first made it.
    """
    written = []
    for look_at in sorted({row["look_at"] for row in rows}):
        of_look = [row for row in rows if row["look_at"] == look_at]
        path = folder / f"{look_at[:16].replace(':', '')}.csv"
        if path.exists():
            with path.open(newline="") as file:
                before = sum(int(row["pixels"]) for row in csv.DictReader(file))
            if before >= sum(row["pixels"] for row in of_look):
                continue
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(of_look[0]))
            writer.writeheader()
            writer.writerows(of_look)
        written.append(path)
    return written


def text(row: dict) -> str:
    """Return the forecast of one front as sentences for a person, with the local time."""
    seen = datetime.fromisoformat(row["look_at"]).astimezone(ZoneInfo(config.DASHBOARD_TIME_ZONE))
    side = ("S" if row["lat"] < 0 else "N", "W" if row["lon"] < 0 else "E")
    place = f"{abs(row['lat']):.2f} {side[0]}, {abs(row['lon']):.2f} {side[1]}"
    last = max(config.FRONT_WINDOWS_H)
    likely = sorted(SECTORS, key=lambda name: -row[f"{name}_{last}"])[:SHOWN_SECTORS]
    lines = [f"A front of {row['pixels']} pixels near {place}, seen at {seen:%H:%M on %-d %B}."]
    for hours in config.FRONT_WINDOWS_H:
        lines.append(
            f"  New ground in {hours} hours: {row[f'new_ground_{hours}']:.0%}. "
            f"{config.FRONT_LARGE_PIXELS} or more new pixels: {row[f'large_growth_{hours}']:.0%}."
        )
    sectors = ", ".join(f"{name} {row[f'{name}_{last}']:.0%}" for name in likely)
    lines.append(f"  The most likely sectors in {last} hours: {sectors}.")
    return "\n".join(lines)
