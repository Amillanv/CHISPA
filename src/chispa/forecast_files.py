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
from chispa.store import to_text

# The form of the two times in the name of a file, in UTC: the look, then when we made the file.
LOOK, MADE = "%Y-%m-%dT%H%M", "%Y-%m-%dT%H%M%S"


def _newest(folder: Path, look_at: str) -> dict | None:
    """Return the newest saved forecast of a look. None: the look has no file."""
    stamp = datetime.fromisoformat(look_at).astimezone(UTC).strftime(LOOK)
    before = sorted(folder.glob(f"{stamp}_*.json"))
    return json.loads(before[-1].read_text()) if before else None


def _size(look: dict) -> tuple[int, int]:
    """Return the pixels in the fronts of a forecast, and its number of fronts with a chance."""
    fronts = look["fronts"]
    return sum(front["pixels"] for front in fronts), sum("no_forecast" not in f for f in fronts)


def is_new(folder: Path, look_at: str, pixels: int) -> bool:
    """Return True if a look has no file, or more pixels in its fronts than in its newest file.

    A look gets more pixels when a second satellite comes. Then it gets a second forecast.
    """
    newest = _newest(folder, look_at)
    return newest is None or _size(newest)[0] < pixels


def save(looks: list[dict], folder: Path, made_at: datetime) -> list[Path]:
    """Save each forecast that adds to the files of its look, and return the new files.

    A forecast adds if its look has no file, or if it has more pixels or more fronts with a
    chance than the newest file. A file has `made_at`, the time when it was complete, also in
    its name. A file never changes: the first forecast of a look stays as we gave it.
    """
    written = []
    for look in looks:
        newest = _newest(folder, look["look_at"])
        size, before = _size(look), _size(newest) if newest else (-1, -1)
        if size[0] <= before[0] and size[1] <= before[1]:
            continue
        stamp = datetime.fromisoformat(look["look_at"]).astimezone(UTC).strftime(LOOK)
        path = folder / f"{stamp}_{made_at.astimezone(UTC).strftime(MADE)}.json"
        if path.exists():
            raise RuntimeError(f"{path} exists: a forecast file does not change. Try again.")
        # A reader must not get a part of a file: the name is final only when the file is complete.
        part = path.with_name(path.name + ".part")
        path.parent.mkdir(parents=True, exist_ok=True)
        part.write_text(json.dumps(look | {"made_at": to_text(made_at)}, indent=1))
        part.rename(path)
        written.append(path)
    return written


def _shown(front: dict, as_of: datetime) -> dict | None:
    """Return a front as the record gives it at the as-of time. None: each window ended."""
    shown = {name: front[name] for name in ("lat", "lon", "pixels", "no_forecast") if name in front}
    # The test found no direction for a small front (`docs/method.md` section 11.30).
    small = front["pixels"] < config.FRONT_SMALL_BELOW
    for name, window in front.items():
        if name.startswith("hours_") and datetime.fromisoformat(window["to"]) > as_of:
            shown[name] = window | ({"sectors": None} if small else {})
    return shown if any(name.startswith("hours_") for name in shown) else None


def of_event(folder: Path, ids: list[int], as_of: datetime) -> dict | None:
    """Return the forecast of one event at the as-of time. None: the event has no forecast.

    `ids` has each issued id of the event at that time. A front is a front of the event if one
    of its pixels is in an alert with one of those ids. The forecast is that of the newest look
    with such a front, from the newest file of the look that was complete at the as-of time.
    A window that ended at the as-of time is not in the answer, and a small front has no sectors.
    """
    longest = max(high for _, high in config.FRONT_WINDOWS_H.values())
    oldest = (as_of - timedelta(hours=longest)).astimezone(UTC).strftime(LOOK)
    now, seen = as_of.astimezone(UTC).strftime(MADE), set()
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
            kept = ("look_at", "made_at", "large_growth_pixels")
            return {name: found[name] for name in kept} | {"fronts": fronts}
    return None
