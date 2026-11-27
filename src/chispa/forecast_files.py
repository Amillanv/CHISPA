"""The files of the live growth forecast: one file for each look, and the forecast of one event.

`evaluation/forecast_live.py` makes a forecast for the fronts of a new look. This module saves
each forecast as a file that does not change, and it gives the event record the forecast of one
event from those files. Thus the record only reads a file: it fits no trees and it gets no
weather. `docs/method.md` section 11.29 gives the rules.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from chispa import config

# The form of the two times in the name of a file, in UTC: the look, then the run.
STAMP = "%Y-%m-%dT%H%M"


def _stamp(time_text: str) -> str:
    return datetime.fromisoformat(time_text).astimezone(UTC).strftime(STAMP)


def is_new(folder: Path, look_at: str, pixels: int) -> bool:
    """Return True if a look has no file, or more pixels in its fronts than in its newest file.

    A look gets more pixels when a second satellite comes. Then it gets a second forecast.
    """
    before = sorted(folder.glob(f"{_stamp(look_at)}_*.json"))
    if not before:
        return True
    newest = json.loads(before[-1].read_text())["fronts"]
    return sum(front["pixels"] for front in newest) < pixels


def save(looks: list[dict], folder: Path) -> list[Path]:
    """Save the forecast of each new look as a new file, and return the new files.

    The name of a file has the time of the look and the time of the run, and a file never
    changes: the first forecast of a look stays as we gave it.
    """
    written = []
    for look in looks:
        pixels = sum(front["pixels"] for front in look["fronts"])
        path = folder / f"{_stamp(look['look_at'])}_{_stamp(look['made_at'])}.json"
        if is_new(folder, look["look_at"], pixels) and not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(look, indent=1))
            written.append(path)
    return written


def _shown(front: dict, as_of: datetime) -> dict | None:
    """Return a front as the record gives it at the as-of time. None: each window ended."""
    shown = {name: front[name] for name in ("lat", "lon", "pixels", "no_forecast") if name in front}
    for hours in config.FRONT_WINDOWS_H:
        window = front.get(f"hours_{hours}", {"to": None})
        if window is None:  # The front has no inputs: no chance, and the reason is in the front.
            shown[f"hours_{hours}"] = None
        elif window["to"] is not None and datetime.fromisoformat(window["to"]) > as_of:
            # The test found no direction for a small front (`docs/method.md` section 11.30).
            small = front["pixels"] < config.FRONT_SMALL_BELOW
            shown[f"hours_{hours}"] = window | ({"sectors": None} if small else {})
    return shown if any(name.startswith("hours_") for name in shown) else None


def of_event(folder: Path, ids: list[int], as_of: datetime) -> dict | None:
    """Return the forecast of one event at the as-of time. None: the event has no forecast.

    `ids` has each issued id of the event at that time. A front is a front of the event if one
    of its pixels is in an alert with one of those ids. The forecast is that of the newest look
    with such a front, from the newest file of the look made at or before the as-of time.
    A window that ended at the as-of time is not in the answer, and a small front has no sectors.
    """
    longest = max(high for _, high in config.FRONT_WINDOWS_H.values())
    now, oldest = (
        time.astimezone(UTC).strftime(STAMP) for time in (as_of, as_of - timedelta(hours=longest))
    )
    seen = set()
    for path in sorted(folder.glob("*.json"), reverse=True):
        look, made = path.stem.split("_")
        if look <= oldest:  # Each window of this look, and of each look before it, ended.
            break
        if made > now or look in seen:
            continue
        seen.add(look)
        found = json.loads(path.read_text())
        own = [front for front in found["fronts"] if set(front["events"]) & set(ids)]
        fronts = [shown for shown in (_shown(front, as_of) for front in own) if shown]
        if fronts:
            times = {"look_at": found["look_at"], "made_at": found["made_at"]}
            return times | {"large_growth_pixels": config.FRONT_LARGE_PIXELS, "fronts": fronts}
    return None
