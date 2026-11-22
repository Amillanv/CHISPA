"""The image check: a person looks at pictures of a sample of the burn check.

The burn check is a rule on numbers. A person must be able to see what the rule saw.
The sample is the start of each event group of the burn check, in a random sequence.
The person does not know the group of an event, or the answer of the rule.
"""

from datetime import datetime
from pathlib import Path

import numpy as np

from chispa import config
from chispa.evaluation import burn
from chispa.evaluation.report import share
from chispa.sources import sentinel2

GROUPS = ("unmatched", "matched")
ANSWERS = ("burned", "not burned", "cannot tell")
BOX = ("south", "west", "north", "east")


def draw(targets: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return the sample for the person and its key, from the targets of the burn check.

    A chip number says nothing about the group. The key gives the group of each chip.
    """
    sizes = dict(zip(GROUPS, (config.IMAGE_SAMPLE, config.IMAGE_CONTROL), strict=True))
    chosen = []
    for group in GROUPS:
        chosen += [target for target in targets if target["group"] == group][: sizes[group]]
    random = np.random.default_rng([config.BURN_SEED, len(burn.GROUPS)])
    sample, key = [], []
    for chip, position in enumerate(random.permutation(len(chosen)).tolist(), start=1):
        target = chosen[position]
        hidden = ("group", "events_in_group", "map_in_box")
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


def write_sample(folder: Path, sample: list[dict], key: list[dict]) -> None:
    """Save the sample, the key and an empty answer file. The person writes only the answers."""
    answers = [{"chip": row["chip"], "answer": "", "note": ""} for row in sample]
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
    for group in GROUPS:
        given = [answer for _, of_group, answer in answers if of_group == group]
        burned, not_burned = given.count("burned"), given.count("not burned")
        rows.append(
            {
                "group": f"{burn.LEVEL} events, {group}",
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
