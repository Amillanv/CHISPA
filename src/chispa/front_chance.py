"""The chance of a front for the alerts of now that only GOES started.

The growth forecast is for a front of VIIRS pixels. An alert that only GOES started has no
front, thus it has no forecast. This module gives such an alert the chance that its event gets a
front in the 24 hours after its first detection. The evaluation fits the model and scores it on
recorded years (`evaluation/front_chance.py`). This module loads the saved model. It reads the
inputs of an alert from the file of its growth risk at 30 minutes (`risk_files.py`): the two
parts have the same inputs at that moment, thus one path makes them. It imports no module of
the evaluation. Each chance is one file that does not change, and the event record reads it.
`docs/method.md` section 11.34 gives the rules.
"""

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

from chispa import confidence, config, fronts, risk_files
from chispa.store import to_text

# The two moments of the growth risk. The chance comes from the inputs of the first moment, one
# pass gap after the first detection. It is for a front before the second moment.
MOMENT, END = "0", "24"
# What a file of the chance keeps from the file of the growth risk of its alert.
KEPT = ("alert", "moment_h", "moment_at", "first_available_at", "lat", "lon", "detections")
KEPT += ("weather_open_meteo_days",)
# What the event record gives from a file of the chance.
SHOWN = ("chance", "until", "moment_at", "made_at", "model", "weather_open_meteo_days")


def only_goes(values: dict[str, float]) -> bool:
    """Return True if each detection of an alert at the moment is a GOES detection.

    `values` has the inputs of the alert: it has one sensor family, and that family is GOES.
    """
    return values["families"] == 1 and values["has_abi"] == 1


def path_of(folder: Path, risk_path: Path) -> Path:
    """Return the file of the chance of an alert, from the file of its growth risk.

    The two files have the same name, in the folder of the same year: the name has the first
    detection of the alert and the moment (`risk_files.path_of`).
    """
    return folder / risk_path.parent.name / risk_path.name


def due(risk_folder: Path, folder: Path, now: datetime) -> list[Path]:
    """Return the file of the growth risk at the first moment of each alert that can get a
    chance now, and has no file of the chance.

    The first moment of the alert is not after now, and its second moment is after now.
    The name of a file starts with the time when CHISPA had the first detection of its alert.
    """
    seconds = confidence.moment_seconds()
    newest, oldest = (now - timedelta(seconds=seconds[moment]) for moment in (MOMENT, END))
    found = []
    for year in sorted({oldest.year, now.year}):
        for path in sorted((risk_folder / str(year)).glob(f"*_{MOMENT}.json")):
            first = datetime.strptime(path.name.split("_")[0], risk_files.FIRST)
            in_time = oldest < first.replace(tzinfo=UTC) <= newest
            if in_time and not path_of(folder, path).exists():
                found.append(path)
    return found


def answer(risk: dict, saved: dict, made_at: datetime) -> dict | None:
    """Return the chance of a front of one alert, as we give it at the time `made_at`.

    `risk` is the file of the growth risk of the alert at the first moment, and `saved` has the
    model. `until` is the second moment of the alert: the chance is for a front before that time.
    None: the alert has no inputs, or it has a detection of a sensor that is not GOES, or
    `made_at` is not before `until`. Then the store has the answer: a chance is not a forecast.
    """
    values = risk.get("inputs")
    first = datetime.fromisoformat(risk["first_available_at"])
    until = first + timedelta(seconds=confidence.moment_seconds()[END])
    if values is None or not only_goes(values) or made_at >= until:
        return None
    model = saved["model"]
    row = np.array([[values[name] for name in model["inputs"]]])
    made = {"chance": round(float(confidence.probability(model, row)[0]), 4)}
    made |= {"until": to_text(until), "model": saved["mark"], "inputs_made_at": risk["made_at"]}
    return {name: risk[name] for name in KEPT} | made | {"made_at": to_text(made_at)}


def update(clock: Callable[[], datetime]) -> str:
    """Make the file of each alert with a new chance, and return one line for `chispa update`.

    This step comes after the growth risk in an update: it reads the files of that step.
    `clock` gives the time of now. Each file gets its own time, for the rule of the second
    moment and for `made_at`: a file does not say a time before we made it.
    """
    saved = risk_files.load_models(config.FRONT_CHANCE_MODEL_PATH)
    if saved is None:
        return "front chance: no saved model of now. Run `chispa forecast --front-chance`."
    folder, new = config.FRONT_CHANCE_LIVE_DIR, 0
    for path in due(config.RISK_LIVE_DIR, folder, clock()):
        made = answer(json.loads(path.read_text()), saved, clock())
        if made is None:
            continue
        try:
            risk_files.write_new(path_of(folder, path), made)
        except FileExistsError:  # A different update made this chance first: it stays.
            continue
        new += 1
    return f"front chance: {new} new files."


def of_event(folder: Path, found: dict, event_id: int, as_of: datetime) -> dict | None:
    """Return the chance of a front of one event at the as-of time. None: it has none then.

    `found` has the detections of the event. The chance is that of the alert that started the
    event, from a file that was complete at the as-of time. It is in the answer only before its
    end, and only while the event has no VIIRS pixel of FIRMS: with such a pixel the event has
    a front, and the question has its answer.
    """
    front = (found["family"] == fronts.SENSOR_FAMILY) & (found["source"] == fronts.SOURCE)
    first = None if front.any() else risk_files.first_of(found, event_id)
    if first is None:
        return None
    path = risk_files.path_of(folder, MOMENT, first)
    if not path.exists():
        return None
    saved = json.loads(path.read_text())
    made, end = (datetime.fromisoformat(saved[name]) for name in ("made_at", "until"))
    if not made <= as_of < end:
        return None
    return {"front_chance": {name: saved[name] for name in SHOWN}}
