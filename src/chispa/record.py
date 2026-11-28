"""The event record: all that CHISPA can say about one event at one time.

An alert, a tool and the dashboard read this one record. It has the state of the event,
the rank of its confidence, its severity, its growth steps, what GOES examined, the growth
forecast of its fronts or the chance of a front, and the growth risk of its first alert.
Each part uses only data that was available at the as-of time, and the event is the event
as it was at that time (`issued.py`). A part that we cannot give is None, with a note.
"""

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from chispa import (
    confidence,
    config,
    forecast_files,
    front_chance,
    growth,
    history,
    risk_files,
    severity,
    view,
)
from chispa.fusion import LEVELS
from chispa.issued import Replay
from chispa.sources import border
from chispa.store import to_text

MERGES = (
    "SELECT CAST(strftime('%s', at) AS INTEGER), absorbed_id, into_id FROM merges WHERE at <= ?"
)
FIELDS = ("lat", "lon", "frp_mw", "family", "platform", "source", "high", "observed", "available")
FIELDS += ("estimated",)
DETECTIONS = """
SELECT d.lat, d.lon, d.frp_mw, d.sensor_family, d.platform, d.source, d.source_confidence = 'high',
       CAST(strftime('%s', d.observed_at) AS INTEGER),
       CAST(strftime('%s', d.available_at) AS INTEGER), d.available_estimated,
       m.level, m.issued_id
FROM detections d JOIN memberships m ON m.detection_id = d.id
WHERE m.issued_id IN ({marks}) AND d.available_at <= ? ORDER BY d.available_at, d.id
"""
NEAR = """
SELECT lat, lon FROM detections
WHERE available_at >= ? AND available_at < ? AND lat >= ? AND lat < ? AND lon >= ? AND lon < ?
"""


def replay_at(store: sqlite3.Connection, as_of: datetime) -> Replay:
    """Return the groups of issued ids as they were at the as-of time."""
    replay = Replay([tuple(row) for row in store.execute(MERGES, (to_text(as_of),))])
    replay.advance(as_of.timestamp())
    return replay


def read(store: sqlite3.Connection, ids: list[int], as_of: datetime) -> dict:
    """Return the detections of an event at the as-of time, as one array for each field.

    The detections are in the sequence in which they became available.
    """
    query = DETECTIONS.format(marks=", ".join("?" * len(ids)))
    rows = store.execute(query, (*ids, to_text(as_of))).fetchall()
    if not rows:
        raise ValueError(f"The event {ids[0]} has no detection at {to_text(as_of)}.")
    columns = list(zip(*rows, strict=True))
    found = {name: np.array(column) for name, column in zip(FIELDS, columns, strict=False)}
    found["frp_mw"] = np.array(columns[2], dtype=float)
    found["level"] = np.array([LEVELS.index(level) for level in columns[10]])
    found["issued"] = np.array(columns[11])
    return found


def state(found: dict, event_id: int, as_of: datetime) -> dict:
    """Return the state of an event from its detections: the level, the times and the place."""
    rises = history.rises(found, event_id)
    last = datetime.fromtimestamp(int(found["observed"].max()), UTC)
    return {
        "event_id": event_id,
        "as_of": to_text(as_of),
        "level": LEVELS[int(found["level"][-1])],
        "level_changes": [
            {"at": _text(found["available"][i]), "level": LEVELS[int(found["level"][i])]}
            for i in rises
        ],
        "detections": len(found["lat"]),
        "sensor_families": sorted(set(found["family"].tolist())),
        "first_observed_at": _text(found["observed"].min()),
        # The fire is this old or older: no source says when it started.
        "hours_from_first_detection": round(
            (as_of.timestamp() - float(found["observed"].min())) / 3600, 2
        ),
        "last_observed_at": to_text(last),
        "newest_available_at": _text(found["available"].max()),
        "newest_observation_age_h": round((as_of - last).total_seconds() / 3600, 2),
        "max_frp_mw": None
        if np.isnan(found["frp_mw"]).all()
        else float(np.nanmax(found["frp_mw"])),
        "lat": round(float(found["lat"].mean()), 5),
        "lon": round(float(found["lon"].mean()), 5),
        "timeline": timeline(found),
    }


def timeline(found: dict) -> list[dict]:
    """Return the detections of an event for each day (UTC), with the sensor families of the day."""
    days = (found["observed"] // 86_400).astype(int)
    return [
        {
            "day": _text(day * 86_400)[:10],
            "detections": int((days == day).sum()),
            "sensor_families": sorted(set(found["family"][days == day].tolist())),
        }
        for day in np.unique(days).tolist()
    ]


def newest_detections(found: dict) -> list[dict]:
    """Return the newest detections of an event, the newest first. `config.py` gives how many."""
    order = np.argsort(-found["observed"], kind="stable")[: config.TOOL_MAX_DETECTIONS]
    return [
        {
            "lat": float(found["lat"][i]),
            "lon": float(found["lon"][i]),
            "observed_at": _text(found["observed"][i]),
            "sensor_family": str(found["family"][i]),
            "platform": str(found["platform"][i]),
            "source": str(found["source"][i]),
            "frp_mw": None if np.isnan(found["frp_mw"][i]) else float(found["frp_mw"][i]),
        }
        for i in order
    ]


def _text(seconds: float) -> str:
    return to_text(datetime.fromtimestamp(int(seconds), UTC))


def growth_steps(found: dict) -> list[dict]:
    """Return each growth step of an event, the oldest first. Less than two VIIRS passes: none.

    A step with no new pixel has no advance: "no measured advance" is not an advance of zero.
    """
    viirs = found["family"] == growth.SENSOR_FAMILY
    if viirs.sum() < 2:
        return []
    observed = found["observed"][viirs].astype(float)
    numbers = growth.passes(found["platform"][viirs], observed)
    return [
        {
            "at": _text(step["at"]),
            "hours_from_the_pass_before": round(step["hours"], 2),
            "new_pixels": step["new_pixels"],
            "advance_m": round(step["advance_m"]) if step["new_pixels"] else None,
            "direction_deg": None
            if step["direction_deg"] is None
            else round(step["direction_deg"]),
            "speed_m_h": None if step["speed_m_h"] is None else round(step["speed_m_h"]),
        }
        for step in growth.steps(found["lat"][viirs], found["lon"][viirs], numbers, observed)
    ]


def near_before(store: sqlite3.Connection, found: dict, event_id: int, inside: Callable) -> int:
    """Return the detections near the first detection of the event, in the days before its day.

    This is the input "activity near the event" of the confidence model: the same days,
    the same cells and only detections in the biome. `inside` says which positions are in the
    biome: it gets the latitudes and the longitudes.
    """
    own = np.nonzero(found["issued"] == event_id)[0]
    first = own[0] if len(own) else 0
    west, south, _, _ = config.PANTANAL_BOX
    side, day_s = config.CONFIDENCE_NEAR_CELL_DEG, 86_400
    day = int(found["available"][first] // day_s)
    row, col = int((found["lat"][first] - south) / side), int((found["lon"][first] - west) / side)
    times = [_text((day - config.CONFIDENCE_NEAR_DAYS) * day_s), _text(day * day_s)]
    box = (
        south + (row - 1) * side,
        south + (row + 2) * side,
        west + (col - 1) * side,
        west + (col + 2) * side,
    )
    places = np.array(store.execute(NEAR, (*times, *box)).fetchall()).reshape(-1, 2)
    return int(inside(places[:, 0], places[:, 1]).sum())


def seen(found: dict, near: int) -> dict:
    """Return what the detections of an event say, for the inputs of `confidence.inputs`."""
    first = int(found["observed"].argmin())
    return {
        "families": set(found["family"].tolist()),
        "has_high": bool(found["high"].any()),
        "day": datetime.fromtimestamp(int(found["observed"][first]), UTC).timetuple().tm_yday,
        "local_hour": (found["observed"][first] / 3600 + found["lon"][first] / 15) % 24,
        "near": near,
    }


def rank(found: dict, facts: dict, near: int, as_of: datetime) -> dict:
    """Return the rank of the confidence of an event, with the inputs that had the largest effect.

    The rank is the share of the alerts of the development year with a smaller value.
    It is not a probability (`docs/method.md` section 11.15).
    """
    hours = (as_of.timestamp() - float(found["available"].min())) / 3600
    moment = "0" if hours < config.SEVERITY_EVAL_HOURS else "24"
    path = config.RESULTS_DIR / str(config.DEVELOPMENT_YEAR) / "confidence" / "model.json"
    model = confidence.load(path)[moment]
    values = confidence.inputs(facts, seen(found, near))
    row = np.array([[values[name] for name in model["inputs"]]])
    value = float(confidence.probability(model, row)[0])
    effects = (
        (row[0] - np.array(model["mean"])) / np.array(model["spread"]) * np.array(model["weights"])
    )
    largest = np.argsort(-np.abs(effects))[:3]
    reference = model["reference"]
    return {
        "model_moment_h": moment,
        # The share of the alerts of the development year with a smaller value.
        "rank": round(float(np.searchsorted(reference, value)) / len(reference), 3),
        "reference_alerts": len(reference),
        "largest_effects": [
            {"input": model["inputs"][i], "effect": round(float(effects[i]), 2)} for i in largest
        ],
    }


def event_record(store: sqlite3.Connection, event_id: int, as_of: datetime, raw_dir: Path) -> dict:
    """Return the record of one event at the as-of time.

    `event_id` can be the id of an alert that merged into an older event before that time.
    Then the record is the record of the older event, and `event_id` in the answer is its id.
    """
    replay = replay_at(store, as_of)
    root = replay.root(event_id)
    found = read(store, replay.ids(event_id), as_of)
    record = state(found, root, as_of)
    steps = growth_steps(found)
    record |= {"growth": steps[-1] if steps else None, "growth_steps": steps, "notes": []}
    shown, count = history.passes(found, root)
    record |= {"passes": history.with_stops(shown, raw_dir), "pass_count": count}
    record["absorbed"] = history.absorbed(replay, root)
    record["newest_detections"] = newest_detections(found)
    last_seen = datetime.fromtimestamp(int(found["observed"].max()), UTC)
    newest = history.newest(found)
    place = (found["lat"][newest], found["lon"][newest])
    record["goes_view"] = view.goes_view(*place, last_seen, as_of, raw_dir)
    record["viirs_passes_after_last_detection"] = view.passes_after(found, as_of, raw_dir)
    ids = replay.ids(event_id)
    forecast = forecast_files.of_event(config.FORECAST_LIVE_DIR, ids, as_of)
    if forecast is None:  # The forecast of a front replaces the chance of a front.
        forecast = front_chance.of_event(config.FRONT_CHANCE_LIVE_DIR, found, root, as_of)
    record["forecast"] = forecast
    record["growth_risk"] = risk_files.of_event(config.RISK_LIVE_DIR, found, root, as_of)
    record |= {"severity": None, "confidence": None}
    return _with_layers(store, record, found, as_of, raw_dir)


def _with_layers(
    store: sqlite3.Connection, record: dict, found: dict, as_of: datetime, raw_dir: Path
) -> dict:
    """Add the severity and the rank of the confidence, which need the layers of the place."""
    root = record["event_id"]
    first_year = datetime.fromtimestamp(int(found["observed"].min()), UTC).year
    try:
        layers = severity.load_layers(raw_dir, severity.cover_year(first_year))
    except RuntimeError as error:
        record["notes"].append(f"No severity and no confidence rank: {error}")
        return record
    advance_m = record["growth"]["advance_m"] if record["growth"] else None
    facts = severity.facts(found["lat"], found["lon"], found["frp_mw"], advance_m, layers)
    value, parts = severity.score(facts)
    record["severity"] = {
        "value": round(value, 1),
        "points": {name: round(points, 1) for name, points in parts.items()},
        "facts": {k: round(v, 2) if isinstance(v, float) else v for k, v in facts.items()},
    }
    rings = border.read_rings(raw_dir / "border" / "pantanal.geojson")
    in_biome = border.rasterize(rings, layers.grid)
    if not in_biome[layers.grid.rows_cols(record["lat"], record["lon"])]:
        record["notes"].append(
            "The event is not in the Pantanal biome of Brazil. The confidence rank, "
            "the land cover and the track record of the level have no check for this place."
        )
    try:
        near = near_before(
            store, found, root, lambda lat, lon: in_biome[layers.grid.rows_cols(lat, lon)]
        )
        record["confidence"] = rank(found, facts, near, as_of)
    except RuntimeError as error:  # The model file is absent. The severity stays.
        record["notes"].append(f"No confidence rank: {error}")
    return record
