"""The event record: all that CHISPA can say about one event at one time.

An alert, a tool and the dashboard read this one record. It has the state of the event,
the rank of its confidence, its severity, its newest growth step and what GOES examined.
Each part uses only data that was available at the as-of time, and the event is the event
as it was at that time (`issued.py`). A part that we cannot give is None, with a note.
"""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from chispa import confidence, config, growth, severity
from chispa.fusion import LEVELS
from chispa.grid import layer_grid
from chispa.issued import Replay
from chispa.sources import border, goes, passes
from chispa.store import to_text

MERGES = (
    "SELECT CAST(strftime('%s', at) AS INTEGER), absorbed_id, into_id FROM merges WHERE at <= ?"
)
FIELDS = ("lat", "lon", "frp_mw", "family", "platform", "source", "high", "observed", "available")
DETECTIONS = """
SELECT d.lat, d.lon, d.frp_mw, d.sensor_family, d.platform, d.source, d.source_confidence = 'high',
       CAST(strftime('%s', d.observed_at) AS INTEGER),
       CAST(strftime('%s', d.available_at) AS INTEGER), m.level, m.issued_id
FROM detections d JOIN memberships m ON m.detection_id = d.id
WHERE m.issued_id IN ({marks}) AND d.available_at <= ? ORDER BY d.available_at, d.id
"""
NEAR = """
SELECT lat, lon FROM detections
WHERE available_at >= ? AND available_at < ? AND lat >= ? AND lat < ? AND lon >= ? AND lon < ?
"""
SAME_PASS_S = 600  # A granule this near to the last detection is a part of its pass.


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
    found["level"] = np.array([LEVELS.index(level) for level in columns[9]])
    found["issued"] = np.array(columns[10])
    return found


def state(found: dict, event_id: int, as_of: datetime) -> dict:
    """Return the state of an event from its detections: the level, the times and the place."""
    rises = np.nonzero(np.diff(np.maximum.accumulate(found["level"]), prepend=-1) > 0)[0]
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
        "last_observed_at": to_text(last),
        "newest_available_at": _text(found["available"].max()),
        "newest_observation_age_h": round((as_of - last).total_seconds() / 3600, 2),
        "max_frp_mw": None
        if np.isnan(found["frp_mw"]).all()
        else float(np.nanmax(found["frp_mw"])),
        "lat": round(float(found["lat"].mean()), 5),
        "lon": round(float(found["lon"].mean()), 5),
    }


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


def newest_step(found: dict) -> dict | None:
    """Return the newest growth step of an event, or None if it has less than two VIIRS passes."""
    viirs = found["family"] == growth.SENSOR_FAMILY
    if viirs.sum() < 2:
        return None
    observed = found["observed"][viirs].astype(float)
    numbers = growth.passes(found["platform"][viirs], observed)
    steps = growth.steps(found["lat"][viirs], found["lon"][viirs], numbers, observed)
    if not steps:
        return None
    step = steps[-1]
    return {
        "at": _text(step["at"]),
        "hours_from_the_pass_before": round(step["hours"], 2),
        "new_pixels": step["new_pixels"],
        "advance_m": round(step["advance_m"]) if step["new_pixels"] else None,
        "direction_deg": None if step["direction_deg"] is None else round(step["direction_deg"]),
        "speed_m_h": None if step["speed_m_h"] is None else round(step["speed_m_h"]),
    }


def near_before(store: sqlite3.Connection, found: dict, event_id: int, in_biome: np.ndarray) -> int:
    """Return the detections near the first detection of the event, in the days before its day.

    This is the input "activity near the event" of the confidence model: the same days,
    the same cells and only detections in the biome.
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
    return int(in_biome[layer_grid().rows_cols(places[:, 0], places[:, 1])].sum())


def rank(found: dict, facts: dict, near: int, as_of: datetime) -> dict:
    """Return the rank of the confidence of an event, with the inputs that had the largest effect.

    The rank is the share of the alerts of the development year with a smaller value.
    It is not a probability (`docs/method.md` section 11.15).
    """
    first = int(found["observed"].argmin())
    hours = (as_of.timestamp() - float(found["available"].min())) / 3600
    moment = "0" if hours < config.SEVERITY_EVAL_HOURS else "24"
    path = config.RESULTS_DIR / str(config.DEVELOPMENT_YEAR) / "confidence" / "model.json"
    model = confidence.load(path)[moment]
    seen = {
        "families": set(found["family"].tolist()),
        "has_high": bool(found["high"].any()),
        "day": datetime.fromtimestamp(int(found["observed"][first]), UTC).timetuple().tm_yday,
        "local_hour": (found["observed"][first] / 3600 + found["lon"][first] / 15) % 24,
        "near": near,
    }
    values = confidence.inputs(facts, seen)
    row = np.array([[values[name] for name in model["inputs"]]])
    value = float(confidence.probability(model, row)[0])
    effects = (
        (row[0] - np.array(model["mean"])) / np.array(model["spread"]) * np.array(model["weights"])
    )
    largest = np.argsort(-np.abs(effects))[:3]
    return {
        "model_moment_h": moment,
        "rank": round(
            float(np.searchsorted(model["reference"], value)) / len(model["reference"]), 2
        ),
        "largest_effects": [
            {"input": model["inputs"][i], "effect": round(float(effects[i]), 2)} for i in largest
        ],
    }


def goes_view(lat: float, lon: float, as_of: datetime, raw_dir: Path) -> dict | None:
    """Return what GOES said for the place in its newest saved scan at or before the as-of time.

    The recorded masks have one scan of each hour. The live masks have each scan of the poller.
    The answer is None if the day of the as-of time has no saved scan before that time.
    """
    for folder in (raw_dir / "goes_mask", raw_dir / "live" / "goes_mask"):
        path = folder / str(as_of.year) / f"{as_of.date()}.npz"
        if not path.exists():
            continue
        day = np.load(path)
        times = [datetime.fromisoformat(str(time)) for time in day["times"]]
        earlier = [number for number, time in enumerate(times) if time <= as_of]
        if not earlier:
            continue
        newest = max(earlier, key=lambda number: times[number])
        place = np.load(folder / "grid.npz")
        nearest = ((place["lat"] - lat) ** 2 + (place["lon"] - lon) ** 2).argmin()
        row, col = np.unravel_index(nearest, place["lat"].shape)
        group = goes.mask_groups(day["mask"][newest, row, col])
        return {"scan_at": to_text(times[newest]), "group": str(group)}
    return None


def passes_after(found: dict, as_of: datetime, raw_dir: Path) -> int | None:
    """Return the VIIRS passes over the event after its last detection. None: no pass list."""
    try:
        granules = passes.read_year(as_of.year, raw_dir)
    except RuntimeError:
        return None
    start, end = float(found["observed"].max()) + SAME_PASS_S, as_of.timestamp()
    lat, lon = float(found["lat"].mean()), float(found["lon"].mean())
    return sum(
        start < time <= end and passes.covers(outline, lat, lon) for _, time, outline in granules
    )


def event_record(store: sqlite3.Connection, event_id: int, as_of: datetime, raw_dir: Path) -> dict:
    """Return the record of one event at the as-of time.

    `event_id` can be the id of an alert that merged into an older event before that time.
    Then the record is the record of the older event, and `event_id` in the answer is its id.
    """
    replay = replay_at(store, as_of)
    root = replay.root(event_id)
    found = read(store, replay.ids(event_id), as_of)
    record = state(found, root, as_of)
    step = newest_step(found)
    record |= {"growth": step, "newest_detections": newest_detections(found), "notes": []}
    record["goes_view"] = goes_view(record["lat"], record["lon"], as_of, raw_dir)
    record["viirs_passes_after_last_detection"] = passes_after(found, as_of, raw_dir)
    try:
        layers = severity.load_layers(raw_dir, _cover_year(raw_dir, as_of.year))
        advance_m = step["advance_m"] if step else None
        facts = severity.facts(found["lat"], found["lon"], found["frp_mw"], advance_m, layers)
        value, parts = severity.score(facts)
        record["severity"] = {
            "value": round(value, 1),
            "points": {name: round(points, 1) for name, points in parts.items()},
            "facts": {k: round(v, 2) if isinstance(v, float) else v for k, v in facts.items()},
        }
        rings = border.read_rings(raw_dir / "border" / "pantanal.geojson")
        in_biome = border.rasterize(rings, layers.grid)
        record["confidence"] = rank(found, facts, near_before(store, found, root, in_biome), as_of)
        if not in_biome[layers.grid.rows_cols(record["lat"], record["lon"])]:
            record["notes"].append(
                "The event is not in the Pantanal biome of Brazil. The confidence rank, "
                "the land cover and the track record of the level have no check for this place."
            )
    except RuntimeError as error:
        record |= {"severity": None, "confidence": None}
        record["notes"].append(f"No severity and no confidence rank: {error}")
    return record


def _cover_year(raw_dir: Path, year: int) -> int:
    """Return the newest land cover year before the year of the event that is on disk."""
    years = [
        int(path.stem) for path in (raw_dir / "landcover").glob("*.npz") if int(path.stem) < year
    ]
    if not years:
        raise RuntimeError(f"There is no land cover before {year}. Run `chispa fetch landcover`.")
    return max(years)
