"""The growth forecast of the fronts: the questions, the models, the baselines and the scores.

For each front at its look, three questions for 12 and for 24 hours: new ground or not, large
growth or not, and a new pixel in each sector or not. Gradient-boosted trees give a probability
for each question from the inputs of `front_inputs.py` (`forecast_model.py`). This module makes
the rows of a question with their answers, and it compares the trees with persistence, the wind
and a logistic regression.
`docs/method.md` section 11.28 gives the rules and the hypothesis.
"""

import sqlite3
from pathlib import Path

import numpy as np

from chispa import config, forecast_model, front_inputs, fronts
from chispa.evaluation import fronts as steps
from chispa.evaluation.confidence import separation
from chispa.evaluation.risk import average_precision


def year_rows(year: int, store_path: Path, raw_dir: Path, in_biome: np.ndarray) -> dict:
    """Return the answers and the inputs of the fronts of one year that count."""
    pixels = fronts.load_pixels(sqlite3.connect(store_path), year)
    masks, layers = steps.open_masks(raw_dir, year), front_inputs.load_layers(raw_dir, year)
    parts = {"answers": [], "inputs": []}
    for a, b, look in fronts.each_look(pixels):
        answers = steps.look_rows(pixels, (a, b), look, masks)
        inputs = front_inputs.look_inputs(pixels, (a, b), look, layers)
        keep = steps.kept(answers, in_biome)
        parts["answers"].append({name: values[keep] for name, values in answers.items()})
        parts["inputs"].append({name: values[keep] for name, values in inputs.items()})
    return {
        kind: {name: np.concatenate([part[name] for part in found]) for name in found[0]}
        for kind, found in parts.items()
    }


def case(rows: dict, question: str, hours: int) -> dict:
    """Return the rows of one question for one year: the inputs, the label and the baselines.

    A row is a front at a place that GOES examined at each time of the window: that does not
    depend on the answer. A front that has no weather on disk, or no pixel with a fire power,
    is not a row. `fronts` is True for each front of the year that is a row, and `small` is
    True for each row of a small front.
    """
    answers, inputs = rows["answers"], rows["inputs"]
    fronts_in = answers[f"examined_{hours}"] & forecast_model.has_inputs(inputs)
    small = answers["pixels"] < config.FRONT_SMALL_BELOW
    use, new = fronts_in, answers[f"new_{hours}"]
    if question == "sector":
        use = np.repeat(fronts_in, config.FRONT_SECTORS)
        small = np.repeat(small, config.FRONT_SECTORS)
        label = (answers[f"sectors_{hours}"] > 0).ravel()
        base = {"persistence": inputs["came_share_s"].ravel()}
        base["wind"] = inputs["past_wind_toward_s"].ravel()
    else:
        least = config.FRONT_LARGE_PIXELS if question == "large_growth" else 1
        label, base = new >= least, {"persistence": inputs["log_came"] + inputs["log_fresh"]}
    table, names = forecast_model.matrix(inputs, question == "sector")
    found = {"x": table[use], "y": label[use].astype(float), "names": names, "fronts": fronts_in}
    found["small"] = small[use]
    return found | {name: values[use] for name, values in base.items()}


def scores(held: dict, chances: dict[str, np.ndarray], training_share: float) -> dict:
    """Return the scores of one question for the rows of one year.

    The Brier skill score compares the trees with the share of the training years: more than 0
    says that the probability is better than that one number. `expected_trees` is the sum of the
    stated chances of the trees: the number of rows with the answer yes that the trees expect.
    """
    label = held["y"]
    row = {"rows": len(label), "positive": int(label.sum())}
    for name in ("persistence", "wind"):
        row[f"auc_{name}"] = separation(held[name], label) if name in held else None
    for name, chance in chances.items():
        row[f"auc_{name}"] = separation(chance, label)
    row["average_precision_trees"] = average_precision(chances["trees"], label > 0)
    alone = float(np.mean((training_share - label) ** 2))
    brier = float(np.mean((chances["trees"] - label) ** 2))
    row["expected_trees"] = round(float(chances["trees"].sum()), 1)
    row["brier_skill_trees"] = round(1 - brier / alone, 4) if alone else None
    return row


def in_45(guess: np.ndarray, truth: np.ndarray, part: np.ndarray) -> int:
    """Return for how many fronts of `part` the two directions agree in 45 degrees."""
    turn = np.abs(guess - truth) % 360
    return int((np.minimum(turn, 360 - turn)[part] <= config.ADVANCE_SAME_DEG).sum())


def directions(chance: np.ndarray) -> np.ndarray:
    """Return the direction of each front from the chances of its sectors, in degrees.

    It is the mean of the sector directions, with the chance of each sector as its weight.
    """
    mean = chance.reshape(-1, config.FRONT_SECTORS) @ front_inputs.units()
    return np.degrees(np.arctan2(mean[:, 1], mean[:, 0])) % 360


def direction_row(rows: dict, held: dict, chances: dict[str, np.ndarray], group: tuple) -> dict:
    """Return how frequently each direction is in 45 degrees of the direction of the new pixels.

    The direction of a model is the mean of the sector directions, with the probability of each
    sector as its weight. Persistence has a direction only for a front with pixels on new ground.
    `group` has the hours of the window, and True for the small fronts or False for the others.
    """
    answers, inputs, (hours, small) = rows["answers"], rows["inputs"], group
    fronts_in = held["fronts"]
    truth = answers[f"direction_deg_{hours}"][fronts_in]
    many = answers[f"new_{hours}"][fronts_in] >= config.FRONT_DIRECTION_PIXELS
    many &= (answers["pixels"][fronts_in] < config.FRONT_SMALL_BELOW) == small
    before = inputs["came_direction_deg"][fronts_in]
    has = many & ~np.isnan(before)
    row = {"hours": hours, "fronts": int(many.sum())}
    for name, chance in chances.items():
        guess = directions(chance)
        row |= {f"{name}_in_45": in_45(guess, truth, many), f"{name}_in_45_of_them": 0}
        row[f"{name}_in_45_of_them"] = in_45(guess, truth, has)
    row["wind_in_45"] = in_45(inputs["wind_direction_deg"][fronts_in], truth, many)
    row |= {
        "fronts_with_persistence": int(has.sum()),
        "persistence_in_45": in_45(before, truth, has),
    }
    return row


def effect_rows(model, held: dict, key: tuple[str, int]) -> list[dict]:
    """Return the inputs with the largest effect on the trees: the decrease of the AUC of the
    year when the values of one input go to different rows."""
    random, table, label = np.random.default_rng(0), held["x"], held["y"]
    whole = separation(model.predict_proba(table)[:, 1], label)
    if whole is None:
        return []
    drops = []
    for number, name in enumerate(held["names"]):
        mixed = table.copy()
        mixed[:, number] = random.permutation(mixed[:, number])
        drops.append((whole - separation(model.predict_proba(mixed)[:, 1], label), name))
    largest = sorted(drops, reverse=True)[: config.FORECAST_EFFECTS]
    return [
        {"question": key[0], "hours": key[1], "input": name, "auc_decrease": round(drop, 4)}
        for drop, name in largest
    ]
