"""The growth forecast of the fronts: the questions, the models, the baselines and the scores.

For each front at its look, three questions for 12 and for 24 hours: new ground or not, large
growth or not, and a new pixel in each sector or not. Gradient-boosted trees give a probability
for each question from the inputs of `front_inputs.py`. This module makes the rows of a question,
fits the models, and compares them with persistence, the wind and a logistic regression.
`docs/method.md` section 11.28 gives the rules and the hypothesis.
"""

import sqlite3
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier

from chispa import config
from chispa.evaluation import front_inputs
from chispa.evaluation import fronts as steps
from chispa.evaluation.confidence import separation
from chispa.evaluation.risk import average_precision

QUESTIONS = ("new_ground", "large_growth", "sector")
# For the baselines and the tables: they are not inputs.
HELPERS = ("came_direction_deg", "wind_direction_deg", "first_look")


def year_rows(year: int, store_path: Path, raw_dir: Path, in_biome: np.ndarray) -> dict:
    """Return the answers and the inputs of the fronts of one year that count."""
    pixels = steps.load_pixels(sqlite3.connect(store_path), year)
    masks, layers = steps.open_masks(raw_dir, year), front_inputs.load_layers(raw_dir, year)
    parts = {"answers": [], "inputs": []}
    for a, b, look in steps.each_look(pixels):
        answers = steps.look_rows(pixels, (a, b), look, masks)
        inputs = front_inputs.look_inputs(pixels, (a, b), look, layers)
        keep = steps.kept(answers, in_biome)
        parts["answers"].append({name: values[keep] for name, values in answers.items()})
        parts["inputs"].append({name: values[keep] for name, values in inputs.items()})
    return {
        kind: {name: np.concatenate([part[name] for part in found]) for name in found[0]}
        for kind, found in parts.items()
    }


def matrix(inputs: dict, by_sector: bool) -> tuple[np.ndarray, tuple[str, ...]]:
    """Return one row of inputs for each front, or for each sector of each front, and the names."""
    front = [name for name in inputs if not name.endswith("_s") and name not in HELPERS]
    if not by_sector:
        return np.column_stack([inputs[name] for name in front]), tuple(front)
    sector = [name for name in inputs if name.endswith("_s")]
    columns = [np.repeat(inputs[name], config.FRONT_SECTORS) for name in front]
    columns += [inputs[name].ravel() for name in sector]
    return np.column_stack(columns), tuple(front + sector)


def case(rows: dict, question: str, hours: int) -> dict:
    """Return the rows of one question for one year: the inputs, the label and the baselines.

    A front that was not visible in the window, or that has no weather on disk, is not a row.
    `fronts` is True for each front of the year that is a row.
    """
    answers, inputs = rows["answers"], rows["inputs"]
    fronts_in = (answers[f"answer_{hours}"] != steps.HIDDEN) & ~np.isnan(inputs["past_vpd"])
    use, new = fronts_in, answers[f"new_{hours}"]
    if question == "sector":
        use = np.repeat(fronts_in, config.FRONT_SECTORS)
        label = (answers[f"sectors_{hours}"] > 0).ravel()
        base = {"persistence": inputs["came_share_s"].ravel()}
        base["wind"] = inputs["past_wind_toward_s"].ravel()
    else:
        least = config.FRONT_LARGE_PIXELS if question == "large_growth" else 1
        label, base = new >= least, {"persistence": inputs["log_came"] + inputs["log_fresh"]}
    table, names = matrix(inputs, question == "sector")
    found = {"x": table[use], "y": label[use].astype(float), "names": names, "fronts": fronts_in}
    return found | {name: values[use] for name, values in base.items()}


def _trees(leaves: int, number: int) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        learning_rate=config.FORECAST_RATE,
        max_iter=number,
        max_leaf_nodes=leaves,
        min_samples_leaf=config.FORECAST_MIN_LEAF,
        l2_regularization=config.FORECAST_PENALTY,
        early_stopping=False,
        random_state=0,
    )


def fit_trees(table: np.ndarray, label: np.ndarray, years: np.ndarray):
    """Return the trees of one question.

    One training year gives the number of trees and of leaves: the year with the second-largest
    number of rows. The first fits do not read it. The last fit reads each training year.
    """
    values, counts = np.unique(years, return_counts=True)
    hold = years == values[np.argsort(counts)[-2]]
    best = (np.inf, 0, 0)
    for leaves in config.FORECAST_LEAVES:
        model = _trees(leaves, config.FORECAST_MAX_TREES).fit(table[~hold], label[~hold])
        for number, chance in enumerate(model.staged_predict_proba(table[hold]), start=1):
            limited = np.clip(chance[:, 1], 1e-6, 1 - 1e-6)
            loss = -np.mean(label[hold] * np.log(limited) + (1 - label[hold]) * np.log(1 - limited))
            best = min(best, (float(loss), leaves, number))
    return _trees(best[1], best[2]).fit(table, label)


def scores(held: dict, chances: dict[str, np.ndarray], training_share: float) -> dict:
    """Return the scores of one question for the rows of one year.

    The Brier skill score compares the trees with the share of the training years: more than 0
    says that the probability is better than that one number.
    """
    label = held["y"]
    row = {"rows": len(label), "positive": int(label.sum())}
    for name in ("persistence", "wind"):
        row[f"auc_{name}"] = separation(held[name], label) if name in held else None
    for name, chance in chances.items():
        row[f"auc_{name}"] = separation(chance, label)
    row["average_precision_trees"] = average_precision(chances["trees"], label > 0)
    brier = float(np.mean((chances["trees"] - label) ** 2))
    alone = float(np.mean((training_share - label) ** 2))
    row |= {"brier_share": round(alone, 4), "brier_trees": round(brier, 4)}
    return row | {"brier_skill": round(1 - brier / alone, 4) if alone else None}


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


def direction_row(rows: dict, hours: int, held: dict, chances: dict[str, np.ndarray]) -> dict:
    """Return how frequently each direction is in 45 degrees of the direction of the new pixels.

    The direction of a model is the mean of the sector directions, with the probability of each
    sector as its weight. Persistence has a direction only for a front with pixels on new ground.
    """
    answers, inputs = rows["answers"], rows["inputs"]
    fronts_in = held["fronts"]
    truth = answers[f"direction_deg_{hours}"][fronts_in]
    many = answers[f"new_{hours}"][fronts_in] >= config.FRONT_DIRECTION_PIXELS
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
