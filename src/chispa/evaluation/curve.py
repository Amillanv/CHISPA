"""The burn curve of the boxes of the burn check: the burned ground some days after an event.

The dark rule says if the ground of a box burned. The burn curve gives that answer at a fixed
number of days after the first detection: for a brigade, for a label of the confidence and for
a target of the growth risk. `docs/method.md` section 11.17 gives the rule and the tables.
"""

import csv
import hashlib
import sqlite3
import statistics
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path

from scipy import stats

from chispa import config, earthengine
from chispa.evaluation import burn, candidates
from chispa.evaluation.report import share
from chispa.grid import layer_grid
from chispa.sources import border, sentinel2_ground

FIELDS = ["id", "settings", "day", "views", "clear_share", "burned_ha"]
LABELS = {
    "unmatched": "HIGH events, unmatched",
    "matched": "HIGH events, matched",
    "no fire": "boxes, no fire",
    "LOW": "LOW events",
    "MEDIUM": "MEDIUM events",
    "HIGH": "HIGH events",
}
# The four pairs of the answer of the curve and of the map, for one event.
PAIRS = {
    "burned_and_match": (True, True),
    "burned_no_match": (True, False),
    "match_no_burn": (False, True),
    "no_burn_no_match": (False, False),
}
EVENTS = (
    "SELECT id, level, lat, lon, south, west, north, east, first_observed_at, last_observed_at "
    "FROM events WHERE id >= ? AND id < ? AND first_observed_at <= ? ORDER BY id"
)


def rule() -> tuple[tuple[float, float], float]:
    """Return the dNBR step and the dark limit of the selected rule, and its minimum hectares."""
    key, min_ha = config.BURN_CANDIDATES[config.BURN_RULE]
    step, dark = (float(value) for value in key.split("/"))
    return (step, dark), min_ha


def signature() -> str:
    """Return a short mark of each value that changes a curve: the box, the periods and the rule."""
    values = (config.BURN_MARGIN_M, config.BURN_DAYS, config.BURN_PATCH_HA, config.CURVE_DAYS)
    return hashlib.sha256(repr((values, rule())).encode()).hexdigest()[:8]


def event_targets(year: int, store_path: Path, raw_dir: Path, now: datetime) -> list[dict]:
    """Return each event of a year with its centre in the biome: its box, its times and its level.

    The level is the group of the event in the table. An event whose last day of the curve is
    not some days in the past is not in the list: its images are not all there.
    """
    newest = now - timedelta(days=max(config.CURVE_DAYS) + config.CURVE_WAIT_DAYS)
    store = sqlite3.connect(store_path)
    store.row_factory = sqlite3.Row
    first_id = year * 10_000_000
    found = store.execute(EVENTS, (first_id, first_id + 10_000_000, newest.isoformat())).fetchall()
    grid = layer_grid()
    in_biome = border.rasterize(border.read_rings(raw_dir / "border" / "pantanal.geojson"), grid)
    targets = []
    for row in found:
        if in_biome[grid.rows_cols(row["lat"], row["lon"])]:
            box = {name: row[name] for name in ("south", "west", "north", "east")}
            times = {name: row[name] for name in ("first_observed_at", "last_observed_at")}
            targets.append({"id": row["id"], "group": row["level"], **box, **times})
    return targets


def _measure(target: dict) -> list[dict]:
    """Return one row for each day of the curve of one box. A day with no answer has empty values.

    A day counts from the first detection. The images of a day start after the last detection,
    as for the selected rule: an event that still burns at a day has no answer at that day.
    """
    box = burn.with_margin(*(float(target[name]) for name in ("south", "west", "north", "east")))
    first = datetime.fromisoformat(target["first_observed_at"])
    before, after = burn.periods(first, datetime.fromisoformat(target["last_observed_at"]))
    ends = {day: min(first + timedelta(days=day), after[1]) for day in config.CURVE_DAYS}
    request = partial(sentinel2_ground.burned_by_day, box, before, after[0], ends, rule()[0])
    found = earthengine.again(request)
    start = {"id": target["id"], "settings": signature()}
    return [
        {**start, "day": day, **dict(zip(FIELDS[3:], found.get(day, ("", "", "")), strict=True))}
        for day in config.CURVE_DAYS
    ]


def measure(targets: list[dict], path: Path, one=None, fields: tuple = ()) -> None:
    """Measure the curve of each target that is not in the file, and append it to the file.

    Each box is saved immediately. Thus a run that stops can continue.
    A file with different columns, or with curves of different values, stops the run.
    `one` and `fields` are for a different measure of a box with the same file rules.
    """
    one, fields = one or _measure, list(fields) or FIELDS
    old = burn.read(path) if path.exists() else []
    if old and (list(old[0]) != fields or {row["settings"] for row in old} != {signature()}):
        raise RuntimeError(f"{path} has curves of different settings. Delete it, then run again.")
    done = {row["id"] for row in old}
    open_targets = [target for target in targets if str(target["id"]) not in done]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="") as file, ThreadPoolExecutor(max_workers=8) as workers:
        writer = csv.DictWriter(file, fieldnames=fields)
        if not done:
            writer.writeheader()
        for rows in workers.map(one, open_targets):
            writer.writerows(rows)
            file.flush()


def answer(row: dict) -> bool | None:
    """Return True if the curve calls a box burned at a day, or None with no clear view to it."""
    if float(row["clear_share"] or 0) < config.BURN_MIN_CLEAR:
        return None
    return float(row["burned_ha"] or 0) >= rule()[1]


def last_answers(path: Path) -> dict[int, bool | None]:
    """Return the answer of the curve at its last day for each event in a file of curves."""
    last = max(config.CURVE_DAYS)
    return {int(row["id"]): answer(row) for row in burn.read(path) if int(row["day"]) == last}


def table(targets: list[dict], rows: list[dict]) -> list[dict]:
    """Return, for each group and each day, how many boxes have an answer and how many burned.

    `answer_share` says how frequently Sentinel-2 can give an answer that many days after
    the first detection. `hectares_median` is for the boxes that the curve calls burned.
    `same_as_last_day` compares an answer with the answer of the same box at the last day,
    for the boxes with the two answers (`with_last_day`).
    """
    group_of = {str(target["id"]): target["group"] for target in targets}
    rows = [row for row in rows if row["id"] in group_of]
    last = {r["id"]: answer(r) for r in rows if int(r["day"]) == max(config.CURVE_DAYS)}
    table_rows = []
    for group in (name for name in LABELS if name in group_of.values()):
        for day in config.CURVE_DAYS:
            own = [r for r in rows if group_of[r["id"]] == group and int(r["day"]) == day]
            answers = [answer(row) for row in own]
            burned = [
                float(row["burned_ha"]) for row, found in zip(own, answers, strict=True) if found
            ]
            clear = sum(found is not None for found in answers)
            pairs = [(found, last.get(row["id"])) for row, found in zip(own, answers, strict=True)]
            pairs = [pair for pair in pairs if None not in pair]
            table_rows.append(
                {
                    "group": LABELS[group],
                    "day": day,
                    "boxes": len(own),
                    "answers": clear,
                    "answer_share": share(clear, len(own)),
                    "burned": len(burned),
                    "burned_share": share(len(burned), clear),
                    "hectares_median": round(statistics.median(burned), 2) if burned else None,
                    "with_last_day": len(pairs),
                    "same_as_last_day": sum(early == late for early, late in pairs),
                }
            )
    return table_rows


def check_table(targets: list[dict], rows: list[dict], measures: list[dict]) -> list[dict]:
    """Return, for each group, the curve at its last day against two slower answers for the same
    boxes: the selected rule at the first clear view after the event, and the Monitor map.

    The counts use the boxes where the two answers exist. The rank correlation uses their hectares.
    """
    last = {r["id"]: r for r in rows if int(r["day"]) == max(config.CURVE_DAYS)}
    by_id = {row["id"]: row for row in measures}
    key, min_ha = config.BURN_CANDIDATES[config.BURN_RULE]
    others = {
        "rule": (config.BURN_RULE, key, min_ha),
        "monitor": ("monitor", *config.BURN_CANDIDATES["monitor"]),
    }
    table_rows = []
    for group in burn.GROUPS:
        row = {"group": LABELS[group]}
        ids = [str(t["id"]) for t in targets if t["group"] == group and str(t["id"]) in last]
        for name, (candidate, other_key, other_ha) in others.items():
            pairs = [
                (answer(last[i]), candidates.answer(by_id[i], candidate, other_key, other_ha), i)
                for i in ids
            ]
            pairs = [pair for pair in pairs if pair[0] is not None and pair[1] is not None]
            same = sum(curve == other for curve, other, _ in pairs)
            hectares = [
                (float(last[i]["burned_ha"]), float(by_id[i][other_key] or 0)) for *_, i in pairs
            ]
            varied = len({a for a, _ in hectares}) > 1 and len({b for _, b in hectares}) > 1
            rank = stats.spearmanr(*zip(*hectares, strict=True)).statistic if varied else None
            row |= {f"{name}_boxes": len(pairs), f"{name}_same": same}
            row |= {f"{name}_same_share": share(same, len(pairs))}
            row[f"{name}_rank_correlation"] = round(float(rank), 4) if rank is not None else None
        table_rows.append(row)
    return table_rows


def map_table(targets: list[dict], rows: list[dict], matched: set[int]) -> list[dict]:
    """Return, for each level, the answer of the curve at its last day against the map.

    `matched` has each event with a detection that matches a mapped fire. The table counts the
    events with an answer of the curve: those that the curve calls burned, those with a match,
    and the four pairs of the two answers.
    """
    last = {row["id"]: row for row in rows if int(row["day"]) == max(config.CURVE_DAYS)}
    table_rows = []
    for group in (name for name in LABELS if name in {target["group"] for target in targets}):
        ids = [str(t["id"]) for t in targets if t["group"] == group and str(t["id"]) in last]
        pairs = [(answer(last[i]), int(i) in matched) for i in ids]
        pairs = [pair for pair in pairs if pair[0] is not None]
        counts = {name: pairs.count(pair) for name, pair in PAIRS.items()}
        same = counts["burned_and_match"] + counts["no_burn_no_match"]
        table_rows.append(
            {
                "group": LABELS[group],
                "events": len(pairs),
                "burned": sum(burned for burned, _ in pairs),
                "matched": sum(match for _, match in pairs),
                **counts,
                "same_share": share(same, len(pairs)),
            }
        )
    return table_rows
