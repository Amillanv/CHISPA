"""The rule for a group of inputs of the growth risk, for all years together.

The table `risk_inputs` of each year compares sets of inputs. This module puts the years
together and says, for each set and each model, if the rule is true: a larger mean AUC,
a larger AUC in most years, and a level that is not worse.
`docs/method.md` section 11.22 gives the rule.
"""

import statistics

from chispa import config

NOW = "inputs now"  # The set of the inputs that the models have.
MODEL = ("moment_h", "limit_ha")


def rule_table(by_year: dict[int, list[dict]], removes: set[str]) -> list[dict]:
    """Return one row for each set but the set of now, and each model.

    `by_year` has the table `risk_inputs` of each year. For a set in `removes`, the inputs of
    now are tested against the set, and the inputs that the set removes stay if they pass.
    A different set is tested against the inputs of now, and it is adopted if it passes.
    `models_passed` is the number of models for which the tested side passes.
    """
    facts: dict[tuple, dict] = {}
    for rows in by_year.values():
        for row in rows:
            found = facts.setdefault((row["inputs"], *(row[name] for name in MODEL)), _empty())
            found["auc"].append(row["auc"])
            if row["observed_to_expected_earlier"] is not None:
                found["large"] += row["large"]
                found["expected"] += row["expected_large_earlier"]
                low, high = config.RISK_LEVEL_YEAR
                found["out"] += not low <= row["observed_to_expected_earlier"] <= high
    table = []
    for (name, moment, limit), found in facts.items():
        if name == NOW:
            continue
        tested, other = (
            (facts[(NOW, moment, limit)], found)
            if name in removes
            else (found, facts[(NOW, moment, limit)])
        )
        table.append(
            {"inputs": name, "moment_h": moment, "limit_ha": limit}
            | {"tested": NOW if name in removes else name}
            | _compare(tested, other)
        )
    for row in table:
        passed = sum(other["passes"] for other in table if other["inputs"] == row["inputs"])
        row["models_passed"] = passed
        row["stays"] = passed >= config.RISK_RULE_MIN_MODELS
    return table


def _empty() -> dict:
    return {"auc": [], "large": 0, "expected": 0.0, "out": 0}


def _compare(tested: dict, other: dict) -> dict:
    """Return the three conditions of the rule for the tested side against the other side."""
    level, other_level = (side["large"] / side["expected"] for side in (tested, other))
    years = sum(one > two for one, two in zip(tested["auc"], other["auc"], strict=True))
    larger = statistics.mean(tested["auc"]) > statistics.mean(other["auc"])
    # The level is not worse if it is not farther from 1 by more than the margin, and if not
    # more years are out of the range of one year.
    near = abs(level - 1) <= abs(other_level - 1) + config.RISK_RULE_LEVEL_MARGIN
    return {
        "auc_mean": round(statistics.mean(tested["auc"]), 4),
        "auc_mean_other": round(statistics.mean(other["auc"]), 4),
        "years_larger": years,
        "years": len(tested["auc"]),
        "level": round(level, 4),
        "level_other": round(other_level, 4),
        "years_out": tested["out"],
        "years_out_other": other["out"],
        "passes": bool(
            larger
            and years >= config.RISK_RULE_MIN_YEARS
            and near
            and tested["out"] <= other["out"]
        ),
    }
