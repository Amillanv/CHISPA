"""Candidates for the burned ground of an event, on the boxes of the burn check.

The box rule of the burn check is weak. Each candidate answers the same question for the same
boxes: did the ground burn? The table gives, for each setting of each candidate, the matched
events that it calls burned and the no-fire boxes that it calls burned.
`docs/method.md` section 11.16 gives the candidates and the measures.
"""

import csv
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from chispa import config
from chispa.evaluation import burn
from chispa.evaluation.report import share
from chispa.sources import monitor, sentinel1, sentinel2

GROUPS = {"matched": "found", "no fire": "no_fire", "unmatched": "unmatched"}


def settings() -> list[tuple[str, str]]:
    """Return each candidate with each key of its measures, as (candidate, key)."""
    steps, darks = config.BURN_DNBR_STEPS, config.BURN_DARK_STEPS
    rows = [("box rule", str(step)) for step in steps]
    rows += [("dark rule", f"{step}/{dark}") for step in steps for dark in darks]
    short = config.BURN_NBR2_STEPS
    rows += [("short-wave rule", f"nbr2:{step}/{dark}") for step in short for dark in darks]
    rows += [("monitor", "monitor")]
    rows += [
        (f"radar {band}", f"{band}/{step}")
        for band in sentinel1.BANDS
        for step in config.RADAR_DB_STEPS
    ]
    return rows


def _measure(target: dict) -> dict:
    """Return the measures of each candidate for one box. An absent value is an empty text."""
    box = burn.with_margin(*(float(target[name]) for name in ("south", "west", "north", "east")))
    first = datetime.fromisoformat(target["first_observed_at"])
    last = datetime.fromisoformat(target["last_observed_at"])
    periods = burn.periods(first, last)
    found = {
        **sentinel2.burned_areas(box, *periods),
        **sentinel1.changed_areas(box, *periods),
        "monitor": monitor.burned_ha(box, first, last),
    }
    keys = ("clear_share", "scenes", *(key for _, key in settings()))
    return {"id": target["id"], **{key: found.get(key, "") for key in keys}}


def measure(targets: list[dict], path: Path) -> None:
    """Measure each target that is not in the file of measures, and append it to the file.

    Each answer is saved immediately. Thus a run that stops can continue.
    """
    done = {row["id"] for row in burn.read(path)} if path.exists() else set()
    open_targets = [target for target in targets if str(target["id"]) not in done]
    fields = ["id", "clear_share", "scenes", *(key for _, key in settings())]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="") as file, ThreadPoolExecutor(max_workers=8) as workers:
        writer = csv.DictWriter(file, fieldnames=fields)
        if not done:
            writer.writeheader()
        for row in workers.map(_measure, open_targets):
            writer.writerow(row)
            file.flush()


def answer(row: dict, candidate: str, key: str, min_ha: float) -> bool | None:
    """Return True if a candidate calls a box burned, or None if it has no answer for the box.

    A Sentinel-2 rule needs a clear view. Radar needs a scene before and a scene after.
    The monthly map has an answer for each box.
    """
    if candidate.startswith("radar") and not float(row["scenes"] or 0):
        return None
    if candidate.endswith("rule") and float(row["clear_share"] or 0) < config.BURN_MIN_CLEAR:
        return None
    return float(row[key] or 0) >= min_ha


def table(targets: list[dict], measures: list[dict], all_settings: bool) -> list[dict]:
    """Return one row for each candidate, key and minimum area, with its counts in each group.

    `difference` is the found share minus the no-fire share. `best` marks the largest difference
    of a candidate: the first such row, thus the lowest step and the smallest area.
    `chosen` marks the setting in `config.py`. The development year needs all settings to set it.
    A different year has only the chosen settings, and no mark for the best.
    """
    by_id = {row["id"]: row for row in measures}
    rows = []
    for (candidate, key), min_ha in (
        (pair, ha) for pair in settings() for ha in config.BURN_HA_STEPS
    ):
        row = {"candidate": candidate, "key": key, "min_ha": min_ha}
        for group, name in GROUPS.items():
            answers = [
                answer(by_id[str(target["id"])], candidate, key, min_ha)
                for target in targets
                if target["group"] == group
            ]
            clear = sum(found is not None for found in answers)
            row |= {f"{name}_boxes": len(answers), f"{name}_answers": clear}
            row |= {f"{name}_burned": answers.count(True)}
            row[f"{name}_share"] = share(answers.count(True), clear)
        both = row["found_share"] is not None and row["no_fire_share"] is not None
        row["difference"] = round(row["found_share"] - row["no_fire_share"], 4) if both else None
        rows.append(row)
    frozen = config.BURN_CANDIDATES or {}
    for row in rows:
        row["chosen"] = "yes" if frozen.get(row["candidate"]) == (row["key"], row["min_ha"]) else ""
    if not all_settings:
        return [row for row in rows if row["chosen"]]
    for candidate in dict.fromkeys(row["candidate"] for row in rows):
        own = [
            row for row in rows if row["candidate"] == candidate and row["difference"] is not None
        ]
        top = max(own, key=lambda row: row["difference"], default=None)
        for row in rows:
            if row["candidate"] == candidate:
                row["best"] = "yes" if row is top else ""
    return rows


def person_table(answers: list[tuple[str, str, str]], measures: list[dict]) -> list[dict]:
    """Return, for the setting of each candidate in `config.py`, its agreement with a person.

    An answer is (id, group, answer of the person). Only the answers "burned" and "not burned"
    count, and only where the candidate has an answer. The events that the person saw with
    an opinion are not in the table.
    """
    by_id = {row["id"]: row for row in measures}
    rows = []
    for candidate, (key, min_ha) in config.BURN_CANDIDATES.items():
        pairs = [
            (given == "burned", answer(by_id[event], candidate, key, min_ha))
            for event, _, given in answers
            if given in ("burned", "not burned") and event not in config.IMAGE_NOT_BLIND
        ]
        yes = [found for person, found in pairs if person and found is not None]
        no = [found for person, found in pairs if not person and found is not None]
        agree = yes.count(True) + no.count(False)
        rows.append(
            {
                "candidate": candidate,
                "key": key,
                "min_ha": min_ha,
                "chips": len(yes) + len(no),
                "person_burned": len(yes),
                "found": yes.count(True),
                "found_share": share(yes.count(True), len(yes)),
                "person_not_burned": len(no),
                "called_burned": no.count(True),
                "false_share": share(no.count(True), len(no)),
                "agree": agree,
                "agree_share": share(agree, len(yes) + len(no)),
            }
        )
    return rows
