"""The growth risk of the alerts of now, from the saved models.

The evaluation scores the growth risk on recorded years. This module makes the growth risk of
each new alert at its two moments: the same inputs and the same models, with no answer yet.
It loads the saved models and the known outcomes (`risk_files.py`), and it imports no module of
the evaluation. It gets the weather that is absent (`risk_weather.py`). The answer of an alert
at a moment is one JSON object in a file that does not change, and the event record reads it.
`docs/method.md` section 11.35 gives the rules.
"""

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

from chispa import confidence, config, record, risk, risk_files, risk_weather, severity
from chispa.grid import pantanal_grid
from chispa.sources import border, weather
from chispa.store import to_text

ALERTS = """
SELECT m.issued_id, MIN(CAST(strftime('%s', d.available_at) AS INTEGER))
FROM detections d JOIN memberships m ON m.detection_id = d.id
WHERE m.issued_id >= ? GROUP BY m.issued_id
"""
OWN = """
SELECT m.issued_id, CAST(strftime('%s', d.available_at) AS INTEGER),
       CAST(strftime('%s', d.observed_at) AS INTEGER), d.lat, d.lon
FROM detections d JOIN memberships m ON m.detection_id = d.id
WHERE d.available_at >= ? AND m.issued_id >= ?
"""
EARLIER = """
SELECT d.lat, d.lon, CAST(strftime('%s', d.available_at) AS INTEGER), d.sensor_family, m.issued_id
FROM detections d JOIN memberships m ON m.detection_id = d.id
WHERE d.available_at >= ? AND d.available_at < ?
AND d.lat >= ? AND d.lat < ? AND d.lon >= ? AND d.lon < ?
"""
NOT_FIRST = "the first detection is not in the Pantanal biome of Brazil"
ONLY_GOES = "only GOES rows of INPE"
NEAR_EARLIER = "near an earlier alert"


@dataclass(frozen=True)
class Layers:
    """What the inputs of the alerts of one year read: the layers of the place, the border of
    the biome, and the inputs of the ground that burned in the years before."""

    places: severity.Layers
    rings: list[np.ndarray]
    ground: dict[str, np.ndarray]

    def in_biome(self, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
        """Return True for each position in the biome, by the rule of the evaluation: the
        pixel of the scar grid that holds the position has its centre in the border."""
        return border.contains(self.rings, pantanal_grid(), lat, lon)


def load_layers(raw_dir: Path, year: int) -> Layers:
    """Return the layers for the alerts of one year: the year of their first detection, also
    for a moment in January of the next year. The evaluation gives an alert the layers of the
    year of the alert."""
    places = severity.load_layers(raw_dir, severity.cover_year(year))
    rings = border.read_rings(raw_dir / "border" / "pantanal.geojson")
    return Layers(places, rings, risk.ground_before(raw_dir, year))


def due(store: sqlite3.Connection, now: datetime, folder: Path) -> list[tuple]:
    """Return (alert, moment, its first detection) for each moment of an alert with no file.

    A moment counts if it is in the last days (`config.py`) and not after the time of now.
    """
    since, moments = now - timedelta(days=config.RISK_LIVE_DAYS), confidence.moment_seconds()
    # An alert of the days before the window can have its last moment in the window.
    oldest = since - timedelta(seconds=max(moments.values()))
    first_id = oldest.year * config.EVENT_IDS_OF_A_YEAR
    started = dict(store.execute(ALERTS, (first_id,)))
    own: dict[int, list] = {}
    for alert, *row in store.execute(OWN, (to_text(oldest), first_id)):
        if started[alert] == row[0]:
            own.setdefault(alert, []).append(tuple(row))
    found = []
    for alert, rows in own.items():
        first = risk_files.first_detection(rows)
        for moment, seconds in moments.items():
            in_time = since.timestamp() <= first[0] + seconds <= now.timestamp()
            if in_time and not risk_files.path_of(folder, moment, first).exists():
                found.append((alert, moment, first))
    return sorted(found, key=lambda one: (one[2][0], one[0], one[1]))


def event_at(store: sqlite3.Connection, alert: int, at: datetime, layers: Layers) -> dict | str:
    """Return the detections in the biome of the event of an alert at a time, or why it has no
    answer: the alert is a part of an older event at that time, or it did not start in the biome.
    """
    replay = record.replay_at(store, at)
    if replay.root(alert) != alert:
        return f"a part of the event {replay.root(alert)} at the moment"
    found = record.read(store, replay.ids(alert), at)
    own = found["issued"] == alert
    names = ("available", "observed", "lat", "lon")
    rows = zip(*(found[name][own].tolist() for name in names), strict=True)
    _, _, lat, lon = risk_files.first_detection(rows)
    if not layers.in_biome(np.array([lat]), np.array([lon]))[0]:
        return NOT_FIRST
    keep = layers.in_biome(found["lat"], found["lon"])
    return {name: values[keep] for name, values in found.items()}


def near_earlier(store: sqlite3.Connection, found: dict, alert: int, layers: Layers) -> dict | None:
    """Return the nearest detection of an earlier alert near this alert, or None.

    A detection counts if it is in the biome, if it was available before the first detection of
    the alert and not more than some days before it, and if it is in no alert of the event.
    `config.py` has the days and the distance.
    """
    first_s = int(found["available"][found["issued"] == alert].min())
    reach = config.RISK_NEAR_EARLIER_M / 100_000  # In degrees: more than the distance.
    days = timedelta(days=config.RISK_NEAR_EARLIER_DAYS)
    start = datetime.fromtimestamp(first_s, UTC)
    box = (found["lat"].min() - reach, found["lat"].max() + reach)
    box += (found["lon"].min() - reach, found["lon"].max() + reach)
    rows = store.execute(EARLIER, (to_text(start - days), to_text(start), *map(float, box)))
    own = set(found["issued"].tolist())
    rows = [row for row in rows if row[4] not in own]
    if not rows:
        return None
    lat, lon, available, family, issued = (np.array(column) for column in zip(*rows, strict=True))
    distance = risk.distance_m((found["lat"], found["lon"]), (lat, lon))
    near = (distance <= config.RISK_NEAR_EARLIER_M) & layers.in_biome(lat, lon)
    if not near.any():
        return None
    nearest = int(np.argmin(np.where(near, distance, np.inf)))
    return {
        "alert": int(issued[nearest]),
        "distance_m": round(float(distance[nearest])),
        "hours_before": round((first_s - int(available[nearest])) / 3600, 1),
        "detections": int(near.sum()),
        "sensor_families": sorted(set(family[near].tolist())),
    }


def inputs(store: sqlite3.Connection, found: dict, alert: int, layers: Layers) -> dict[str, float]:
    """Return the inputs of an alert that do not need the weather: those of the confidence,
    the first hours, and the ground that burned before."""
    steps = record.growth_steps(found)
    advance_m = steps[-1]["advance_m"] if steps else None
    facts = severity.facts(found["lat"], found["lon"], found["frp_mw"], advance_m, layers.places)
    near = record.near_before(store, found, alert, layers.in_biome)
    values = confidence.inputs(facts, record.seen(found, near))
    values |= risk.first_hours_inputs(found, np.arange(len(found["lat"])))
    spot = layers.places.grid.rows_cols(found["lat"].mean(), found["lon"].mean())
    return values | {name: float(layer[spot]) for name, layer in layers.ground.items()}


def answer(one: dict, saved: dict) -> dict:
    """Return the answer of one alert at one moment from its inputs and the saved models.

    `one` has the alert, its inputs and its marks. An alert with only GOES rows of INPE, and an
    alert near an earlier alert, get the rank of each limit and no chance.
    """
    values = one.pop("values")
    found = risk.limits(saved, values, one["moment_h"], one.pop("at_s"))
    if one["no_percentage"]:
        found = [limit | {"chance": None} for limit in found]
    made = {"models_made_at": saved["made_at"], "map_months": saved["map"]}
    inputs = {name: round(value, risk.DIGITS) for name, value in values.items()}
    return one | {"limits": found, "inputs": inputs} | made


def read_alert(store: sqlite3.Connection, waiting: tuple, layers: Layers) -> dict:
    """Return what one alert has at one moment, with no weather: its times, its place, its
    marks and its inputs. An alert with no answer has the reason, and no inputs."""
    alert, moment, first = waiting
    at_s = first[0] + confidence.moment_seconds()[moment]
    at = datetime.fromtimestamp(at_s, UTC)
    one = {"alert": alert, "moment_h": moment, "moment_at": to_text(at)}
    one |= {"first_available_at": to_text(datetime.fromtimestamp(first[0], UTC))}
    one |= {"first_observed_at": to_text(datetime.fromtimestamp(first[1], UTC))}
    one |= {"first_lat": first[2], "first_lon": first[3]}
    found = event_at(store, alert, at, layers)
    if isinstance(found, str):
        return one | {"no_answer": found}
    earlier = near_earlier(store, found, alert, layers)
    only_goes = risk.only_inpe_goes(found, np.arange(len(found["lat"])))
    place = float(found["lat"].mean()), float(found["lon"].mean())
    return one | {
        # The weather cell of the place, and the day of the moment: `add_weather` reads them.
        "cell": tuple(int(index) for index in weather.weather_grid().rows_cols(*place)),
        "day": at.date(),
        "detections": len(found["lat"]),
        "lat": round(place[0], 5),
        "lon": round(place[1], 5),
        "near_earlier": earlier,
        "no_percentage": ONLY_GOES if only_goes else NEAR_EARLIER if earlier else None,
        "values": inputs(store, found, alert, layers),
        "at_s": at_s,
    }


def late_weather(one: dict, days: risk_weather.Days) -> dict[str, float] | None:
    """Return the weather inputs of one alert, and put its number of Open-Meteo days in it.

    None: the weather has no value at the place, for example in a cell of water.
    """
    series, era5 = risk_weather.series(days, one.pop("cell"))
    late_day = (one.pop("day") - days.start).days - config.RISK_WEATHER_LATE_DAYS
    if len(series["rain_mm"]) < late_day:
        raise RuntimeError("The weather does not have each day before this alert. Try again.")
    one["weather_open_meteo_days"] = max(late_day - era5, 0)
    late = risk.late_weather_inputs(series, late_day + config.RISK_WEATHER_LATE_DAYS)
    return None if np.isnan(list(late.values())).any() else late


def add_weather(read: list[dict], raw_dir: Path, project: str | None) -> list[dict]:
    """Return each alert that was read with its weather inputs, or with the reason for no answer."""
    late_days = config.RISK_WEATHER_LATE_DAYS
    asked = [one for one in read if "no_answer" not in one]
    if not asked:
        return read
    first = min(one["day"] for one in asked) - timedelta(days=late_days + 95)
    need = max(one["day"] for one in asked) - timedelta(days=late_days + 1)
    days = risk_weather.load(raw_dir, first, need, {one["cell"] for one in asked}, project)
    found = []
    for one in read:
        late = None if "no_answer" in one else late_weather(one, days)
        if "no_answer" not in one and late is None:
            one = {name: value for name, value in one.items() if name not in ("values", "at_s")}
            one["no_answer"] = "the weather has no value at the place"
        elif late is not None:
            one["values"] |= late
        found.append(one)
    return found


def read_all(
    store: sqlite3.Connection, raw_dir: Path, waiting: list[tuple], project: str | None
) -> list[dict]:
    """Return each waiting alert at its moment with each of its inputs, or with the reason for
    no answer. `waiting` has (alert, moment, its first detection)."""
    layers: dict[int, Layers] = {}
    read = []
    for one in waiting:
        year = datetime.fromtimestamp(one[2][0], UTC).year
        if year not in layers:
            layers[year] = load_layers(raw_dir, year)
        read.append(read_alert(store, one, layers[year]))
    return add_weather(read, raw_dir, project)


def answers(
    store: sqlite3.Connection, raw_dir: Path, waiting: list[tuple], project: str | None
) -> list[dict] | None:
    """Return the answer of each waiting alert. None: no saved models are those of now."""
    saved = risk_files.load_models(config.RISK_MODELS_PATH)
    if saved is None:
        return None
    saved["past"] = risk_files.as_arrays(saved["past"])
    read = read_all(store, raw_dir, waiting, project)
    return [one if "no_answer" in one else answer(one, saved) for one in read]


def update(store_path: Path, raw_dir: Path, now: datetime, pull: tuple) -> str:
    """Make the file of each alert with a new moment, and return one line for `chispa update`.

    A layer or the weather can be absent. Then the line says so: the update is complete with
    no answer, and the next update does this step again.
    """
    note = risk_files.keep_current(store_path, raw_dir, now, pull)
    store, folder = sqlite3.connect(store_path), config.RISK_LIVE_DIR
    waiting = due(store, now, folder)
    try:
        made = answers(store, raw_dir, waiting, pull[0]) if waiting else []
    except (RuntimeError, OSError, ValueError) as error:
        return f"growth risk: no answer. {error}"
    if made is None:
        return f"growth risk: no saved models. {note or 'The next update makes them.'}"
    for one in made:
        risk_files.save(one, folder, datetime.now(UTC))
    chances = [[limit["chance"] for limit in one.get("limits", [])] for one in made]
    count = sum(any(chance is not None for chance in of_one) for of_one in chances)
    line = f"growth risk: {len(made)} new files, {count} with a percentage."
    return f"{line} {note}" if note else line
