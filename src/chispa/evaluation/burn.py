"""The burn check: ask Sentinel-2 if the ground at an event burned.

An event with no mapped fire is not always a false alarm: the map does not show each fire.
For each event we compare the burn ratio before and after it (dNBR), in the box of the event.
Two reference groups say what the answer is worth: events that match a mapped fire,
and boxes with no detection and no mapped fire. `images.py` lets a person check the answers.
"""

import csv
import itertools
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from chispa import config
from chispa.evaluation.events import events_with_a_match
from chispa.evaluation.match import Fields, Pairs
from chispa.evaluation.report import share
from chispa.evaluation.run import prepare
from chispa.grid import Grid, pantanal_grid
from chispa.sources import border, sentinel2_ground

LEVEL = "HIGH"
GROUPS = ("unmatched", "matched", "no fire")
EVENT = (
    "SELECT id, south, west, north, east, first_observed_at, last_observed_at "
    "FROM events WHERE id = ?"
)
TRIES = 200  # The number of random positions that we try for one box with no fire.

Box = tuple[float, float, float, float]  # south, west, north, east


def groups(detections: Fields, pairs: Pairs, final_level: dict) -> dict[str, list[int]]:
    """Return the HIGH events of the biome in two groups: with no match and with a match."""
    matched = events_with_a_match(detections, pairs)
    events = [e for e in np.unique(detections["event"]).tolist() if final_level[e] == LEVEL]
    return {
        "unmatched": [event for event in events if event not in matched],
        "matched": [event for event in events if event in matched],
    }


def order(events: list[int], group: str) -> list[int]:
    """Return the events in a random sequence with a fixed seed.

    A sample is the start of this sequence. Thus a small sample is a part of a larger sample.
    """
    random = np.random.default_rng([config.BURN_SEED, GROUPS.index(group)])
    return [sorted(events)[position] for position in random.permutation(len(events)).tolist()]


def with_margin(south: float, west: float, north: float, east: float) -> Box:
    """Return the box that we examine: the box of the event plus the margin on each side."""
    d_lat = config.BURN_MARGIN_M / 110_574
    d_lon = config.BURN_MARGIN_M / (111_320 * float(np.cos(np.deg2rad((south + north) / 2))))
    return south - d_lat, west - d_lon, north + d_lat, east + d_lon


def periods(first: datetime, last: datetime) -> tuple[tuple, tuple]:
    """Return the period before an event and the period after it.

    The period before ends at the start of the day of the first detection: the fire is not in it.
    """
    days = timedelta(days=config.BURN_DAYS)
    day_start = first.replace(hour=0, minute=0, second=0)
    return (first - days, day_start), (last + timedelta(days=1), last + days)


def free_boxes(models: list[dict], detections: Fields, numbers: np.ndarray, grid: Grid, raw: Path):
    """Give boxes with no fire: no mapped fire of the year, and no detection near the time.

    Each box has the size and the times of one model event, at a random position in the biome.
    A model with no free position in the set number of tries gives no box.
    """
    random = np.random.default_rng([config.BURN_SEED, GROUPS.index("no fire")])
    west, south, east, north = config.PANTANAL_BOX
    lats = random.uniform(south, north, len(models) * TRIES)
    lons = random.uniform(west, east, len(models) * TRIES)
    in_biome = border.rasterize(border.read_rings(raw / "border" / "pantanal.geojson"), grid)
    inside = in_biome[grid.rows_cols(lats, lons)]
    del in_biome
    margin_s = config.BURN_DAYS * 86_400
    for number, model in enumerate(models):
        half_lat, half_lon = (
            (model["north"] - model["south"]) / 2,
            (model["east"] - model["west"]) / 2,
        )
        start = datetime.fromisoformat(model["first_observed_at"]).timestamp() - margin_s
        end = datetime.fromisoformat(model["last_observed_at"]).timestamp() + margin_s
        in_time = (detections["observed"] >= start) & (detections["observed"] <= end)
        for position in (
            np.nonzero(inside[number * TRIES : (number + 1) * TRIES])[0] + number * TRIES
        ):
            lat, lon = float(lats[position]), float(lons[position])
            box = (lat - half_lat, lon - half_lon, lat + half_lat, lon + half_lon)
            if _is_free(with_margin(*box), detections, in_time, numbers, grid):
                keys = ("south", "west", "north", "east")
                yield {**model, "id": f"box{number + 1}", **dict(zip(keys, box, strict=True))}
                break


def _is_free(box: Box, detections: Fields, in_time: np.ndarray, numbers: np.ndarray, grid) -> bool:
    south, west, north, east = box
    lat, lon = detections["lat"], detections["lon"]
    if (in_time & (lat >= south) & (lat <= north) & (lon >= west) & (lon <= east)).any():
        return False
    return not has_mapped_fire(box, numbers, grid)


def has_mapped_fire(box: Box, numbers: np.ndarray, grid: Grid) -> bool:
    """Return True if the box holds a pixel of a mapped fire of the year."""
    south, west, north, east = box
    (top, bottom), (left, right) = grid.rows_cols(np.array([north, south]), np.array([west, east]))
    return bool(numbers[max(top, 0) : bottom + 1, max(left, 0) : right + 1].any())


def make_targets(year: int, store_path: Path, raw_dir: Path) -> list[dict]:
    """Return each box that the burn check examines, with its group and its times.

    The groups: each HIGH event with no match, a sample of the HIGH events with a match,
    and boxes with no fire. `events_in_group` is the number of events before the sample.
    `map_in_box` says if the box holds a pixel of a mapped fire of the year. An event with no
    match can have one: the fire burned at a different time, or outside the reach of the match.
    """
    detections, pairs, _, final_level = prepare(year, store_path, raw_dir)
    found = groups(detections, pairs, final_level)
    store = sqlite3.connect(store_path)
    store.row_factory = sqlite3.Row
    targets = []
    for group, size in (("unmatched", len(found["unmatched"])), ("matched", config.BURN_CONTROL)):
        for event in order(found[group], group)[:size]:
            row = dict(store.execute(EVENT, (event,)).fetchone())
            targets.append({"group": group, "events_in_group": len(found[group]), **row})
    models = [targets[n % len(found["unmatched"])] for n in range(config.BURN_CONTROL)]
    numbers, grid = np.load(store_path.parent / "fires" / f"{year}.npz")["numbers"], pantanal_grid()
    for box in free_boxes(models, detections, numbers, grid, raw_dir):
        targets.append({**box, "group": "no fire", "events_in_group": ""})
    for target in targets:
        box = with_margin(*(target[name] for name in ("south", "west", "north", "east")))
        target["map_in_box"] = "yes" if has_mapped_fire(box, numbers, grid) else "no"
    return targets


def _measure(target: dict) -> dict:
    box = with_margin(*(float(target[name]) for name in ("south", "west", "north", "east")))
    first = datetime.fromisoformat(target["first_observed_at"])
    last = datetime.fromisoformat(target["last_observed_at"])
    areas = sentinel2_ground.burned_areas(box, *periods(first, last))
    steps = {str(step): areas.get(str(step), "") for step in config.BURN_DNBR_STEPS}
    start = {"id": target["id"], "clear_share": areas["clear_share"]}
    return {**start, "background": areas.get("background", ""), **steps}


def measure(targets: list[dict], path: Path) -> None:
    """Measure each target that is not in the file of measures, and append it to the file.

    Each answer is saved immediately. Thus a run that stops can continue.
    """
    done = {row["id"] for row in read(path)} if path.exists() else set()
    open_targets = [target for target in targets if str(target["id"]) not in done]
    fields = ["id", "clear_share", "background", *(str(step) for step in config.BURN_DNBR_STEPS)]
    with path.open("a", newline="") as file, ThreadPoolExecutor(max_workers=8) as workers:
        writer = csv.DictWriter(file, fieldnames=fields)
        if not done:
            writer.writeheader()
        for row in workers.map(_measure, open_targets):
            writer.writerow(row)
            file.flush()


def read(path: Path) -> list[dict]:
    """Return the rows of one file of the burn check."""
    with path.open(newline="") as file:
        return list(csv.DictReader(file))


def write(path: Path, rows: list[dict]) -> None:
    """Save rows as one file of the burn check."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def is_burned(measure_row: dict, step: float, min_ha: float) -> bool | None:
    """Return the answer of the rule for one dNBR step and one minimum area.

    The answer is None if the view is not clear.
    """
    if float(measure_row["clear_share"]) < config.BURN_MIN_CLEAR:
        return None
    return float(measure_row[str(step)]) >= min_ha


def table(targets: list[dict], measures: list[dict], all_pairs: bool) -> list[dict]:
    """Return, for each group, how many boxes the rule calls burned.

    `all_pairs` gives one row for each dNBR step and minimum area: the development year needs
    them to set the rule. If not, the table has only the pair that `config.py` sets.
    `clear` is the number of boxes with an answer. `burned_share` is burned divided by clear.
    The second row is a part of the first row: the events with no mapped fire in their box.
    """
    by_id = {row["id"]: row for row in measures}
    chosen = (config.BURN_DNBR_MIN, config.BURN_HA_MIN)
    pairs = (
        itertools.product(config.BURN_DNBR_STEPS, config.BURN_HA_STEPS) if all_pairs else [chosen]
    )
    parts = (
        (f"{LEVEL} events, unmatched", "unmatched", ("yes", "no")),
        (f"{LEVEL} events, unmatched, no mapped fire in the box", "unmatched", ("no",)),
        (f"{LEVEL} events, matched", "matched", ("yes", "no")),
        ("boxes, no fire", "no fire", ("yes", "no")),
    )
    rows = []
    for (step, min_ha), (name, group, in_box) in itertools.product(pairs, parts):
        of_part = [t for t in targets if t["group"] == group and t["map_in_box"] in in_box]
        answers = [is_burned(by_id[str(target["id"])], step, min_ha) for target in of_part]
        clear = sum(answer is not None for answer in answers)
        rows.append(
            {
                "group": name,
                "events": next((t["events_in_group"] for t in of_part), "")
                if len(in_box) == 2
                else "",
                "sample": len(of_part),
                "clear": clear,
                "dnbr_step": step,
                "min_ha": min_ha,
                "burned": answers.count(True),
                "burned_share": share(answers.count(True), clear),
                "chosen": "yes" if (step, min_ha) == chosen else "",
            }
        )
    return rows


def rule_table(targets: list[dict], measures: list[dict]) -> list[dict]:
    """Return the quality of the chosen rule on the two reference groups, as one row.

    Recall: the matched events that the rule calls burned. False share: the no-fire boxes that
    the rule calls burned. Precision and F1 use the two groups together, thus they are true
    only for this mix of the groups, not for all events.
    """
    by_id = {row["id"]: row for row in measures}
    counts = {}
    for group in ("matched", "no fire"):
        answers = [
            is_burned(by_id[str(t["id"])], config.BURN_DNBR_MIN, config.BURN_HA_MIN)
            for t in targets
            if t["group"] == group
        ]
        counts[group] = (answers.count(True), sum(answer is not None for answer in answers))
    (found, fires), (false, boxes) = counts["matched"], counts["no fire"]
    return [
        {
            "reference_fires": fires,
            "called_burned": found,
            "recall": share(found, fires),
            "reference_boxes_no_fire": boxes,
            "boxes_called_burned": false,
            "false_share": share(false, boxes),
            "precision": share(found, found + false),
            "f1": share(2 * found, 2 * found + false + fires - found),
        }
    ]
