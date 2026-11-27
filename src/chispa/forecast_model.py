"""The model of the growth forecast: its questions, its inputs, its trees and the saved trees.

Gradient-boosted trees give a chance for each question of a front from the inputs of
`front_inputs.py`. This module makes the matrix of the inputs, fits the trees, and saves and
loads the trees of a live forecast. It reads no answer: `evaluation/forecast.py` makes the rows
with the answers and the scores, and `evaluation/forecast_trees.py` fits the saved trees.
Thus a live forecast loads a file, as the confidence does (`confidence.py`).
`docs/method.md` sections 11.28 and 11.29 give the rules.
"""

import hashlib
import pickle
from pathlib import Path

import numpy as np
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier

from chispa import config, front_inputs, fronts
from chispa.evaluation.report import config_hash

QUESTIONS = ("new_ground", "large_growth", "sector")
# For the baselines and the tables: they are not inputs.
HELPERS = ("came_direction_deg", "wind_direction_deg", "first_look")


def matrix(inputs: dict, by_sector: bool) -> tuple[np.ndarray, tuple[str, ...]]:
    """Return one row of inputs for each front, or for each sector of each front, and the names."""
    front = [name for name in inputs if not name.endswith("_s") and name not in HELPERS]
    if not by_sector:
        return np.column_stack([inputs[name] for name in front]), tuple(front)
    sector = [name for name in inputs if name.endswith("_s")]
    columns = [np.repeat(inputs[name], config.FRONT_SECTORS) for name in front]
    columns += [inputs[name].ravel() for name in sector]
    return np.column_stack(columns), tuple(front + sector)


def has_inputs(inputs: dict) -> np.ndarray:
    """Return True for each front with the inputs that a row needs: the weather before its look
    on disk, and a pixel with a fire power. The trees have no row and no score for the others."""
    return ~np.isnan(inputs["past_vpd"]) & ~np.isnan(inputs["log_frp_mean"])


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


def inputs_mark() -> str:
    """Return a mark of what makes the inputs of a front: the configuration, the code of the
    fronts, of the inputs and of this module, and the version of scikit-learn.

    Saved trees are for the inputs of their mark. A live forecast does not use other trees.
    """
    files = (fronts.__file__, front_inputs.__file__, __file__)
    code = "".join(Path(file).read_text() for file in files)
    made_from = f"{code}{sklearn.__version__}".encode()
    return config_hash() + hashlib.sha256(made_from).hexdigest()[:12]


def save_trees(models: dict, names: dict, trees: str) -> None:
    """Save the trees of each question with their input names. `trees` is the mark of the fit."""
    saved = {"inputs": inputs_mark(), "trees": trees, "models": models, "names": names}
    config.FORECAST_MODELS_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.FORECAST_MODELS_PATH.write_bytes(pickle.dumps(saved))


def load_trees() -> dict | None:
    """Return the saved trees. None: no file, or trees for other inputs than those of now.

    `chispa forecast --trees` fits the trees and saves them: some minutes.
    """
    path = config.FORECAST_MODELS_PATH
    if not path.exists():
        return None
    saved = pickle.loads(path.read_bytes())
    return saved if saved.get("inputs") == inputs_mark() else None
