"""The calibration of the growth risk: its values against what came.

A percentage in an alert is correct only if, of the alerts with a value near 0.1, approximately
1 in 10 became large. This module makes the table that examines it.
`docs/method.md` section 11.21 gives the rules.
"""

import numpy as np

from chispa import confidence, config
from chispa.evaluation.confidence import MOMENTS, as_table
from chispa.evaluation.report import share

TENTHS = 10  # The groups of the table. A fifth is too wide for a rare outcome.


def calibration_table(kept: dict[str, list], models: dict) -> list[dict]:
    """Return, for each model, the values of the growth risk against what came.

    The first row of a model is for all alerts, with the Brier score and its skill against one
    constant: the base rate of the training years. Then one row for each tenth of the alerts,
    in the sequence of the value. `above_lower_limit` counts the alerts with a larger value
    than for the lower limit: their two values give no probability for the class between.
    """
    table = []
    for moment in MOMENTS:
        rows, lower = kept[moment], None
        size = np.array([row["size_ha"] for row in rows])
        for limit in config.RISK_LIMITS_HA:
            model = models[f"{moment}h_{limit:g}ha"]
            chance = confidence.probability(model, as_table(rows, tuple(model["inputs"]))[0])
            large = size >= limit
            brier = float(((chance - large) ** 2).mean())
            constant = float(((model["base_rate"] - large) ** 2).mean())
            first = _row(chance, large) | {
                "brier": round(brier, 5),
                # With no large alert in the training years and in the year, the constant has
                # no error: the skill has no value.
                "brier_skill": round(1 - brier / constant, 4) if constant else None,
                "above_lower_limit": None if lower is None else int((chance > lower).sum()),
            }
            parts = np.array_split(np.argsort(chance, kind="stable"), TENTHS)
            groups = [("all", first)] + [
                (str(number), _row(chance[part], large[part]))
                for number, part in enumerate(parts, 1)
            ]
            table += [
                {"moment_h": moment, "limit_ha": limit, "group": name} | row for name, row in groups
            ]
            lower = chance
    return table


def _row(chance: np.ndarray, large: np.ndarray) -> dict:
    # With less alerts than groups, a group has no alert: its mean is absent, not a number.
    return {
        "alerts": len(large),
        "probability_mean": round(float(chance.mean()), 4) if len(chance) else None,
        "large": int(large.sum()),
        "large_share": share(large.sum(), len(large)),
        "expected_large": round(float(chance.sum()), 1),
        "observed_to_expected": share(large.sum(), chance.sum()),
    }
