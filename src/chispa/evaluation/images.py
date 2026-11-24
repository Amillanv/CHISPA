"""The image check: a person looks at pictures of a sample of the burn check.

The burn check is a rule on numbers. A person must be able to see what the rule saw.
The sample is the start of each event group of the burn check, in a random sequence.
The person does not know the group of an event, or the answer of the rule.
A second look has the same events again and boxes with no fire, with one more picture of each.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from chispa import config
from chispa.evaluation import burn
from chispa.evaluation.report import share
from chispa.sources import sentinel2

GROUPS = ("unmatched", "matched")
ANSWERS = ("burned", "not burned", "cannot tell")
BOX = ("south", "west", "north", "east")
VIEWS = ("before", "after", "later")  # The pictures of one chip of the second look.


def draw(targets: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return the sample for the person and its key, from the targets of the burn check.

    A chip number says nothing about the group. The key gives the group of each chip.
    """
    sizes = dict(zip(GROUPS, (config.IMAGE_SAMPLE, config.IMAGE_CONTROL), strict=True))
    chosen = []
    for group in GROUPS:
        chosen += [target for target in targets if target["group"] == group][: sizes[group]]
    return _number(chosen, [config.BURN_SEED, len(burn.GROUPS)], ())


def draw_second(targets: list[dict], first_key: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return the sample and the key of the second look.

    With a first look, it has each event of that look again, and the first no-fire boxes of the
    burn check. With no first look, it has the start of each group, with the sizes in `config.py`.
    A new random sequence gives new chip numbers. The sample has no id: the id of a box
    shows its group.
    """
    if first_key:
        seen = {row["id"] for row in first_key}
        sizes = {"no fire": config.IMAGE_NO_FIRE}
        chosen = [target for target in targets if target["id"] in seen]
    else:
        sizes, chosen = config.IMAGE_TEST_SAMPLE, []
    for group, size in sizes.items():
        chosen += [target for target in targets if target["group"] == group][:size]
    return _number(chosen, [config.BURN_SEED, len(burn.GROUPS), 2], ("id",))


def _number(
    chosen: list[dict], seed: list[int], more_hidden: tuple
) -> tuple[list[dict], list[dict]]:
    """Give each target a chip number in a random sequence. Return the sample and its key."""
    random = np.random.default_rng(seed)
    hidden = ("group", "events_in_group", "map_in_box", *more_hidden)
    sample, key = [], []
    for chip, position in enumerate(random.permutation(len(chosen)).tolist(), start=1):
        target = chosen[position]
        sample.append({"chip": chip, **{k: v for k, v in target.items() if k not in hidden}})
        key.append({"chip": chip, "id": target["id"], "group": target["group"]})
    return sample, key


def get_pictures(sample: list[dict], folder: Path) -> None:
    """Save the picture before and the picture after each event. Add the image names to the rows.

    A row with no image in the permitted days gets an empty name. A picture on disk stays.
    """
    for row in sample:
        outline = tuple(float(row[name]) for name in BOX)
        box = burn.with_margin(*outline)
        first = datetime.fromisoformat(row["first_observed_at"])
        last = datetime.fromisoformat(row["last_observed_at"])
        before, after = burn.periods(first, last)
        for name, period, newest in (("before", before, True), ("after", after, False)):
            image = sentinel2.find_image(box, *period, newest)
            row[f"{name}_image"], row[f"{name}_cloud"] = image or ("", "")
            path = folder / f"{row['chip']:03d}_{name}.png"
            if image and not path.exists():
                sentinel2.save_picture(image[0], box, outline, path)


def choose_views(views: list[tuple], first: datetime, last: datetime) -> dict[str, tuple | None]:
    """Return the pictures of one chip: the last clear view before the event, the first clear view
    after it, and one later view. A view is (name, time, cloud-free share of the box).

    The later view shows if a dark area stays. A burn stays. A cloud shadow or water does not.
    """
    before, after = burn.periods(first, last)
    clear = [view for view in views if view[2] >= config.IMAGE_MIN_CLEAR]
    old = [view for view in clear if before[0] <= view[1] < before[1]]
    new = [view for view in clear if after[0] <= view[1] <= after[1]]
    chosen = {"before": old[-1] if old else None, "after": new[0] if new else None, "later": None}
    if new:
        start = new[0][1] + timedelta(days=config.IMAGE_LATER_MIN_DAYS)
        end = last + timedelta(days=config.IMAGE_LATER_DAYS)
        later = [view for view in clear if start <= view[1] <= end]
        chosen["later"] = later[0] if later else None
    return chosen


def get_views(sample: list[dict], folder: Path) -> None:
    """Save the pictures of the second look. Add the image names and the cloud-free shares."""

    def one_chip(row: dict) -> None:
        outline = tuple(float(row[name]) for name in BOX)
        box = burn.with_margin(*outline)
        first = datetime.fromisoformat(row["first_observed_at"])
        last = datetime.fromisoformat(row["last_observed_at"])
        start = first - timedelta(days=config.BURN_DAYS)
        end = last + timedelta(days=config.IMAGE_LATER_DAYS)
        chosen = choose_views(sentinel2.cloud_free_views(box, start, end), first, last)
        for number, name in enumerate(VIEWS, start=1):
            view = chosen[name]
            row[f"{name}_image"] = view[0] if view else ""
            row[f"{name}_cloud_free"] = round(view[2], 3) if view else ""
            path = folder / f"{row['chip']:03d}_{number}_{name}.png"
            if view and not path.exists():
                sentinel2.save_picture(view[0], box, outline, path)

    # Each chip needs some requests to Earth Engine. Some chips at one time are quicker.
    with ThreadPoolExecutor(max_workers=8) as workers:
        list(workers.map(one_chip, sample))


def write_sample(folder: Path, sample: list[dict], key: list[dict]) -> None:
    """Save the sample, the key and an empty answer file. The person writes only the answers.

    `area` is for a chip with the answer "burned": `small` or `large`, against the white square.
    """
    blank = {"answer": "", "area": "", "note": ""}
    answers = [{"chip": row["chip"], **blank} for row in sample]
    for name, rows in (("sample", sample), ("key", key), ("answers", answers)):
        burn.write(folder / f"{name}.csv", rows)


def read_answers(folder: Path) -> list[tuple[str, str, str]]:
    """Return (event, group, answer of the person) for each chip."""
    answers = {
        row["chip"]: row["answer"].strip().lower() for row in burn.read(folder / "answers.csv")
    }
    wrong = sorted({answer for answer in answers.values() if answer and answer not in ANSWERS})
    if wrong:
        raise ValueError(f"Unknown answers {wrong}. Use one of {ANSWERS}, or no text.")
    return [
        (row["id"], row["group"], answers[row["chip"]]) for row in burn.read(folder / "key.csv")
    ]


def count(answers: list[tuple[str, str, str]]) -> list[dict]:
    """Return one row for each group: how many chips got each answer of the person.

    `burned_share` uses only the chips with the answer "burned" or "not burned".
    """
    rows = []
    for group in burn.GROUPS:
        given = [answer for _, of_group, answer in answers if of_group == group]
        if not given:
            continue
        burned, not_burned = given.count("burned"), given.count("not burned")
        label = "boxes, no fire" if group == "no fire" else f"{burn.LEVEL} events, {group}"
        rows.append(
            {
                "group": label,
                "sample": len(given),
                "burned": burned,
                "not_burned": not_burned,
                "cannot_tell": given.count("cannot tell"),
                "no_answer": sum(answer not in ANSWERS for answer in given),
                "burned_share": share(burned, burned + not_burned),
            }
        )
    return rows


def agreement(answers: list[tuple[str, str, str]], measures: list[dict]) -> list[dict]:
    """Return, for each answer of the person, what the burn check says for the same events."""
    by_id = {row["id"]: row for row in measures}
    rows = []
    for given in ANSWERS:
        rule = [
            burn.is_burned(by_id[event], config.BURN_DNBR_MIN, config.BURN_HA_MIN)
            for event, _, answer in answers
            if answer == given
        ]
        rows.append(
            {
                "person": given,
                "chips": len(rule),
                "rule_burned": rule.count(True),
                "rule_not_burned": rule.count(False),
                "rule_no_clear_view": rule.count(None),
            }
        )
    return rows
