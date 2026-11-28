"""The files of the live growth risk: the saved models, and one file for each alert and moment.

`risk_live.py` makes the growth risk of an alert at its moment. This module saves each answer
as a file that does not change, and it gives the event record the answers of one event from
those files. Thus the record only reads a file: it gets no weather and it reads no model.
A later run can score the files against what came: they are data that no model has read.
`docs/method.md` section 11.35 gives the rules.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from chispa.config_hash import config_hash
from chispa.store import to_text

# The name of each moment in the event record.
NAMES = {"0": "at_30_minutes", "24": "at_24_hours"}


def save_models(saved: dict, path: Path) -> None:
    """Save what a live alert needs as one file, with the configuration that made it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # An update can load the file at the moment of a save. It must not read a part of the file,
    # and a save that stops must not lose the file that exists: the name changes last.
    part = path.with_name(path.name + ".part")
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


def path_of(folder: Path, alert: int, moment: str) -> Path:
    """Return the file of one alert at one moment. An alert id starts with its year."""
    return folder / str(alert)[:4] / f"{alert}_{moment}.json"


def save(answer: dict, folder: Path, made_at: datetime) -> Path:
    """Save the answer of one alert at one moment, and return its file.

    The file has `made_at`: the time when it was complete. A file never changes: the answer
    stays as we gave it.
    """
    path = path_of(folder, answer["alert"], answer["moment_h"])
    if path.exists():
        raise RuntimeError(f"{path} exists: a file of the growth risk does not change.")
    # A reader must not get a part of a file: the name is final only when the file is complete.
    part = path.with_name(path.name + ".part")
    path.parent.mkdir(parents=True, exist_ok=True)
    part.write_text(json.dumps(answer | {"made_at": to_text(made_at)}, indent=1))
    part.rename(path)
    return path


def of_event(folder: Path, found: dict, event_id: int, as_of: datetime) -> dict | None:
    """Return the growth risk of one event at the as-of time. None: it has no file.

    `found` has the detections of the event. The answers are those of the alert that started
    the event, for each moment with a file that was complete at the as-of time. A file is of
    this alert only if it has the time of its first detection: an id can go to a different
    alert when the store gets older rows.
    """
    own = found["available"][found["issued"] == event_id]
    if not len(own):
        return None
    first = to_text(datetime.fromtimestamp(int(own.min()), UTC))
    answers = {}
    for moment, name in NAMES.items():
        path = path_of(folder, event_id, moment)
        if not path.exists():
            continue
        answer = json.loads(path.read_text())
        made = datetime.fromisoformat(answer["made_at"])
        if made <= as_of and answer["first_available_at"] == first:
            # The inputs stay in the file: the record has what a person reads.
            answers[name] = {key: value for key, value in answer.items() if key != "inputs"}
    return answers or None


def as_arrays(past: dict[str, dict[str, list]]) -> dict[str, dict[str, np.ndarray]]:
    """Return the known outcomes of each model as arrays: the time, the value and the label."""
    return {
        name: {field: np.array(values, dtype=float) for field, values in of_model.items()}
        for name, of_model in past.items()
    }
