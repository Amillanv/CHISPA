"""The files of the live growth risk: the saved models, and one file for each alert and moment.

`risk_live.py` makes the growth risk of an alert at its moment. This module saves each answer
as a file that does not change, and it gives the event record the answers of one event from
those files. Thus the record only reads a file: it gets no weather and it reads no model.
It also loads the saved models, and it asks for new ones when they are absent or old.
A later run can score the files against what came: they are data that no model has read.
`docs/method.md` section 11.35 gives the rules.
"""

import json
import os
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import ee
import numpy as np

from chispa import config
from chispa.config_hash import config_hash
from chispa.store import to_text

# The form of the time of the first detection in the name of a file, in UTC.
FIRST = "%Y%m%dT%H%M%S"
# The first detection of an alert: when it was available and when it was observed, in seconds,
# and its place.
First = tuple[int, int, float, float]
# The name of each moment in the event record.
NAMES = {"0": "at_30_minutes", "24": "at_24_hours"}


def save_models(saved: dict, path: Path) -> None:
    """Save what a live alert needs as one file, with the configuration that made it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # An update can load the file at the moment of a save. It must not read a part of the file,
    # and a save that stops must not lose the file that exists: the name changes last.
    # Two updates can make the file at one time: each has its own part.
    part = path.with_name(f"{path.name}.{os.getpid()}.part")
    part.write_text(json.dumps(saved | {"config": config_hash()}))
    part.replace(path)


def load_models(path: Path) -> dict | None:
    """Return the saved models and outcomes. None: no file, or a file of other settings.

    `chispa update` makes the file (`evaluation/risk_save.py`): some minutes.
    """
    if not path.exists():
        return None
    saved = json.loads(path.read_text())
    return saved if saved.get("config") == config_hash() else None


def keep_current(store_path: Path, raw_dir: Path, now: datetime, pull: tuple) -> str | None:
    """Make the saved models and outcomes again if they are absent, of other settings, or if
    the last look for a new month of the Monitor map is old. Return a note, or None.

    `pull` has the project of Earth Engine and the function that makes the file: the function
    is in the evaluation, and this module does not import it.
    """
    project, refresh = pull
    saved = load_models(config.RISK_MODELS_PATH)
    limit = timedelta(hours=config.RISK_MAP_CHECK_HOURS)
    if saved is not None and now - datetime.fromisoformat(saved["map_checked_at"]) < limit:
        return None
    if not project or refresh is None:
        return None if saved else "Add EE_PROJECT to the file .env: an update then makes them."
    try:
        return refresh(store_path, raw_dir, now, project)
    except (RuntimeError, OSError, ValueError, ee.EEException) as error:
        # The next look is after the usual time, not in the next update. A different update
        # can have made new models in the minutes of this look: the file of now gets the time.
        current = load_models(config.RISK_MODELS_PATH)
        if current is not None:
            save_models(current | {"map_checked_at": to_text(now)}, config.RISK_MODELS_PATH)
        return f"The saved models are not new. {error}"


def first_detection(rows: Iterable[tuple]) -> First:
    """Return the first detection of an alert: its two times and its place.

    `rows` has (available, observed, lat, lon) of each detection of the alert itself. Of the
    detections with the first time when CHISPA had them, it is the first in the sequence of
    the observation time, the latitude and the longitude. No id of the store is in this rule.
    """
    available, observed, lat, lon = min(rows)
    return int(available), int(observed), float(lat), float(lon)


def path_of(folder: Path, moment: str, first: First) -> Path:
    """Return the file of one alert at one moment, in the folder of the year of the alert.

    The name has the first detection of the alert, and not its id: an id can go to a
    different alert when the store gets older rows. Two alerts that came in one poll have the
    same time, thus the name also has the place. Two alerts of one poll can be at one place,
    on different days: thus it also has the observation time.
    """
    available, observed = (datetime.fromtimestamp(time, UTC).strftime(FIRST) for time in first[:2])
    name = f"{available}_{observed}_{first[2]:.5f}_{first[3]:.5f}_{moment}.json"
    return folder / available[:4] / name


def save(answer: dict, folder: Path, made_at: datetime) -> Path:
    """Save the answer of one alert at one moment, and return its file.

    The file has `made_at`: the time when it was complete. A file never changes: the answer
    stays as we gave it. If the file exists, this stops with `FileExistsError`, also when a
    different update made it at the same time.
    """
    times = (answer["first_available_at"], answer["first_observed_at"])
    seconds = [int(datetime.fromisoformat(time).timestamp()) for time in times]
    path = path_of(folder, answer["moment_h"], (*seconds, answer["first_lat"], answer["first_lon"]))
    # A reader must not get a part of a file: the name is final only when the file is complete.
    # Two updates can make one answer at one time: each has its own part, and a link does not
    # replace a file that exists. Thus the second update changes nothing.
    part = path.with_name(f"{path.name}.{os.getpid()}.part")
    path.parent.mkdir(parents=True, exist_ok=True)
    part.write_text(json.dumps(answer | {"made_at": to_text(made_at)}, indent=1))
    try:
        os.link(part, path)
    except FileExistsError:
        message = f"{path} exists: a file of the growth risk does not change."
        raise FileExistsError(message) from None
    finally:
        part.unlink()
    return path


def of_event(folder: Path, found: dict, event_id: int, as_of: datetime) -> dict | None:
    """Return the growth risk of one event at the as-of time. None: it has no file.

    `found` has the detections of the event. The answers are those of the alert that started
    the event, for each moment with a file that was complete at the as-of time. The file of an
    alert has the first detection of the alert in its name (`path_of`).
    """
    own = found["issued"] == event_id
    if not own.any():
        return None
    names = ("available", "observed", "lat", "lon")
    first = first_detection(zip(*(found[name][own].tolist() for name in names), strict=True))
    answers = {}
    for moment, name in NAMES.items():
        path = path_of(folder, moment, first)
        if not path.exists():
            continue
        answer = json.loads(path.read_text())
        if datetime.fromisoformat(answer["made_at"]) <= as_of:
            # The inputs stay in the file: the record has what a person reads.
            answers[name] = {key: value for key, value in answer.items() if key != "inputs"}
    return answers or None


def as_arrays(past: dict[str, dict[str, list]]) -> dict[str, dict[str, np.ndarray]]:
    """Return the known outcomes of each model as arrays: the time, the value and the label."""
    return {
        name: {field: np.array(values, dtype=float) for field, values in of_model.items()}
        for name, of_model in past.items()
    }
