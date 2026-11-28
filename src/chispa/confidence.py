"""Confidence: the probability that an event will match a mapped fire.

The level rule counts passes and sensor families. At the first detection it is almost always
LOW. This module gives a probability from more facts: what the sensors saw, when, on what
ground and near what. The model is a logistic regression: one weight for each input,
thus a person can read why a probability is high or low.
"""

import json
from pathlib import Path

import numpy as np
from scipy import optimize

from chispa import config

FAMILIES = ("abi", "viirs", "modis", "avhrr")
COVERS = ("forest", "savanna", "wetland", "grassland", "pasture", "farming")
INPUTS = (
    "detections_log",
    "families",
    *(f"has_{family}" for family in FAMILIES),
    "has_high",
    "power_log",
    "no_power",
    "season_sin",
    "season_cos",
    "night",
    *(f"on_{cover}" for cover in COVERS),
    "people_log",
    "protected_km_log",
    "indigenous_km_log",
    "near_log",
)
LATER_INPUTS = ("extent_km_log", "has_advance")  # Only at the second moment.
MOMENTS = ("0", "24")  # The two moments of a model, in hours after the first alert.


def moment_seconds() -> dict[str, float]:
    """Return the seconds from the first detection of an alert to each moment.

    The first moment is one pass gap after the first detection: the detections of the first
    pass are complete then.
    """
    return {"0": config.PASS_GAP.total_seconds(), "24": config.SEVERITY_EVAL_HOURS * 3600}


def inputs(found: dict, seen: dict) -> dict[str, float]:
    """Return the inputs of the model for one event at one moment.

    `found` has the facts of `severity.facts`. `seen` has what the detections say:
    the set of sensor families, if a source gave a high confidence, the day of the year,
    the hour at the place of the first detection, and the number of detections near that
    place in the days before.
    """
    angle = 2 * np.pi * seen["day"] / 365.25
    power = found["max_frp_mw"]
    dusk, dawn = config.NIGHT_HOURS
    values = {
        "detections_log": np.log1p(found["detections"]),
        "families": len(seen["families"]),
        "has_high": float(seen["has_high"]),
        "power_log": np.log1p(power) if power is not None else 0.0,
        "no_power": float(power is None),
        "season_sin": np.sin(angle),
        "season_cos": np.cos(angle),
        "night": float(seen["local_hour"] >= dusk or seen["local_hour"] < dawn),
        "people_log": np.log1p(found["people_near"]),
        "protected_km_log": np.log1p(found["protected_km"]),
        "indigenous_km_log": np.log1p(found["indigenous_km"]),
        "near_log": np.log1p(seen["near"]),
        "extent_km_log": np.log1p(found["extent_km"]),
        "has_advance": float(found["advance_m"] is not None),
    }
    values |= {f"has_{family}": float(family in seen["families"]) for family in FAMILIES}
    values |= {f"on_{cover}": float(found["cover"] == cover) for cover in COVERS}
    return {name: float(value) for name, value in values.items()}


def fit(table: np.ndarray, matched: np.ndarray, names: tuple[str, ...]) -> dict:
    """Return a model from one row of inputs for each event and the label of each event.

    Each input gets the mean 0 and the spread 1 first. Thus the weights are comparable.
    The penalty in `config.py` keeps the weights small. `base_rate` is the matched share
    of these events: the probability that a person can give with no model.
    """
    mean, spread = table.mean(axis=0), table.std(axis=0)
    spread[spread == 0] = 1.0
    scaled = (table - mean) / spread

    def loss(weights: np.ndarray) -> tuple[float, np.ndarray]:
        score = weights[0] + scaled @ weights[1:]
        chance = 1 / (1 + np.exp(-score))
        errors = np.logaddexp(0, score) - matched * score
        slope = np.concatenate(
            [[np.mean(chance - matched)], scaled.T @ (chance - matched) / len(matched)]
        )
        slope[1:] += 2 * config.CONFIDENCE_PENALTY * weights[1:]
        return errors.mean() + config.CONFIDENCE_PENALTY * (weights[1:] ** 2).sum(), slope

    best = optimize.minimize(loss, np.zeros(len(names) + 1), jac=True, method="L-BFGS-B")
    return {
        "inputs": list(names),
        "mean": mean.tolist(),
        "spread": spread.tolist(),
        "start": float(best.x[0]),
        "base_rate": float(matched.mean()),
        "weights": best.x[1:].tolist(),
    }


def probability(model: dict, table: np.ndarray) -> np.ndarray:
    """Return the probability of a match for each row of inputs."""
    scaled = (table - np.array(model["mean"])) / np.array(model["spread"])
    return 1 / (1 + np.exp(-(model["start"] + scaled @ np.array(model["weights"]))))


def save(models: dict[str, dict], path: Path) -> None:
    """Save the models of the moments as one file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(models, indent=1))


def load(path: Path) -> dict[str, dict]:
    """Return the models of the moments."""
    if not path.exists():
        year = config.DEVELOPMENT_YEAR
        raise RuntimeError(f"There is no model. Run `chispa confidence --year {year}` first.")
    return json.loads(path.read_text())
