"""The recalibration of the growth risk: its level, corrected with the outcomes that are known.

The share of the alerts that become large changes with the size of the fire season, and no
input has it. At the time of an alert, the outcomes of older alerts are known. This module
compares what the values of those alerts expected with what came, and it corrects the values
of the new alerts with that factor. `docs/method.md` section 11.24 gives the rules.
"""

import numpy as np

from chispa import confidence, config
from chispa.evaluation.confidence import MOMENTS, as_table, separation
from chispa.evaluation.report import share
from chispa.evaluation.risk import key, new_or_none
from chispa.evaluation.risk_calibration import TENTHS, level_row

DAY_S = 86_400
Tables = dict[str, list[dict]]


def factors(times: np.ndarray, past: dict[str, np.ndarray]) -> np.ndarray:
    """Return the factor of each alert from the known outcomes of the alerts before it.

    `past` has the time, the value and the label of the older alerts. An outcome is known if
    its alert is older than the delay, and it counts if it is in the window. The factor is the
    large alerts that came, divided by those that the values expected. The prior is added to
    the two: with few known outcomes, the factor stays near 1.
    """
    order = np.argsort(past["time"], kind="stable")
    ordered = past["time"][order]
    came = np.concatenate([[0.0], np.cumsum(past["large"][order])])
    expected = np.concatenate([[0.0], np.cumsum(past["value"][order])])
    delay = config.RISK_RECALIBRATION_DELAY_DAYS * DAY_S
    window = config.RISK_RECALIBRATION_WINDOW_DAYS * DAY_S
    newest = np.searchsorted(ordered, times - delay, side="right")
    oldest = np.searchsorted(ordered, times - window, side="right")
    prior = config.RISK_RECALIBRATION_PRIOR
    return (came[newest] - came[oldest] + prior) / (expected[newest] - expected[oldest] + prior)


def recalibrate(values: np.ndarray, factor: np.ndarray) -> np.ndarray:
    """Return the values with their odds multiplied by the factor."""
    return values * factor / (1 - values + values * factor)


def recalibration_tables(
    parts: dict[int, dict], models: dict[int, dict], test_year: int | None = None
) -> dict[int, Tables]:
    """Return the tables of the recalibration for each scored year, or for the test year only.

    `models` has, for each year with an earlier year, its models from the earlier years.
    An alert with only GOES rows of INPE gets a rank and no percentage: it is in no table row
    but the count `rank_only_alerts`. A year is scored if it has enough training years.
    The scored years get the table of the conditions, and the test year gets its own table.
    """
    scored = {year: _split(parts[year]["rows"]) for year in models}
    facts = {
        (moment, limit): _facts(scored, models, moment, limit)
        for moment in MOMENTS
        for limit in config.RISK_CLASS_LIMITS_HA
    }
    tables: dict[int, Tables] = {}
    for year in models if test_year is None else [test_year]:
        if sum(other < year for other in parts) < config.RISK_MIN_TRAINING_YEARS:
            continue
        tables[year] = {"risk_recalibrated": [], "risk_classes": []}
        for moment in MOMENTS:
            values = []
            for limit in config.RISK_CLASS_LIMITS_HA:
                value, factor = _corrected(facts[(moment, limit)], year)
                found = _level_rows(facts[(moment, limit)][year], value, factor)
                found[0]["rank_only_alerts"] = len(scored[year][moment][1])
                name = {"moment_h": moment, "limit_ha": limit}
                tables[year]["risk_recalibrated"] += [name | row for row in found]
                values.append(value)
            size = np.array([row["size_ha"] for row in scored[year][moment][0]])
            classes = class_rows(values, size)
            tables[year]["risk_classes"] += [{"moment_h": moment} | row for row in classes]
    if test_year is not None:
        tables[test_year]["risk_test"] = answer_table(tables[test_year]["risk_recalibrated"])
    elif tables:
        by_year = {year: found["risk_recalibrated"] for year, found in tables.items()}
        tables[max(tables)]["risk_percentage"] = percentage_table(by_year)
    return tables


def _split(rows: dict[str, list]) -> dict[str, tuple[list, list]]:
    """Return, for each moment, the alerts that get a percentage and those with a rank only."""
    found = {}
    for moment in MOMENTS:
        kept = new_or_none(rows[moment])
        found[moment] = (
            [row for row in kept if not row["only_inpe_goes"]],
            [row for row in kept if row["only_inpe_goes"]],
        )
    return found


def _facts(scored: dict, models: dict[int, dict], moment: str, limit: float) -> dict[int, dict]:
    """Return, for one model and each year, the time, the value and the label of its alerts."""
    found = {}
    for year, of_year in models.items():
        rows, model = scored[year][moment][0], of_year[key(moment, limit)]
        found[year] = {
            "time": np.array([row["at"] for row in rows]),
            "value": confidence.probability(model, as_table(rows, tuple(model["inputs"]))[0]),
            "large": np.array([row["size_ha"] >= limit for row in rows], dtype=float),
            "base_rate": model["base_rate"],
        }
    return found


def _corrected(facts: dict[int, dict], year: int) -> tuple[np.ndarray, np.ndarray]:
    """Return the new values of one year, and the factor of each alert.

    The known outcomes come from the year and from the year before it, with the values that
    those alerts had at their time.
    """
    older = [facts[one] for one in (year - 1, year) if one in facts]
    past = {
        name: np.concatenate([one[name] for one in older]) for name in ("time", "value", "large")
    }
    factor = factors(facts[year]["time"], past)
    return recalibrate(facts[year]["value"], factor), factor


def _level_rows(facts: dict, value: np.ndarray, factor: np.ndarray) -> list[dict]:
    """Return the level of one model in one year: for all alerts, then for each tenth."""
    before, large = facts["value"], facts["large"]
    constant = float(((facts["base_rate"] - large) ** 2).mean())
    first = _level(value, before, large) | {
        "brier_skill": _skill(value, large, constant),
        "brier_skill_before": _skill(before, large, constant),
        "auc": separation(value, large),
        "factor_smallest": round(float(factor.min()), 4),
        "factor_median": round(float(np.median(factor)), 4),
        "factor_largest": round(float(factor.max()), 4),
    }
    parts = np.array_split(np.argsort(value, kind="stable"), TENTHS)
    tenths = [_level(value[part], before[part], large[part]) for part in parts]
    groups = ["all", *(str(number) for number in range(1, TENTHS + 1))]
    return [{"group": name} | row for name, row in zip(groups, [first, *tenths], strict=True)]


def _level(value: np.ndarray, before: np.ndarray, large: np.ndarray) -> dict:
    return level_row(value, large) | {
        "expected_large_before": round(float(before.sum()), 1),
        "observed_to_expected_before": share(large.sum(), before.sum()),
    }


def _skill(value: np.ndarray, large: np.ndarray, constant: float) -> float | None:
    """Return the Brier skill score against one constant: the base rate of the training years."""
    return round(1 - float(((value - large) ** 2).mean()) / constant, 4) if constant else None


def class_rows(values: list[np.ndarray], size: np.ndarray) -> list[dict]:
    """Return, for each size class, the alerts that ended in it and those that the values expected.

    `values` has the value of each alert for each limit, the smallest limit first. A value for
    a limit that is larger than the value for the limit before it is a wrong sequence: the
    alert then gets the smaller of the two, and the class between gets 0.
    """
    limits = config.RISK_CLASS_LIMITS_HA
    reach = [values[0]]
    for value in values[1:]:
        reach.append(np.minimum(reach[-1], value))
    wrong = int(
        sum((value > lower).sum() for lower, value in zip(values, values[1:], strict=False))
    )
    chances = [1 - reach[0], *(a - b for a, b in zip(reach, reach[1:], strict=False)), reach[-1]]
    edges = [0.0, *limits, np.inf]
    names = [f"less than {limits[0]:g} hectares"]
    names += [f"{a:g} to {b:g} hectares" for a, b in zip(limits, limits[1:], strict=False)]
    names.append(f"{limits[-1]:g} hectares or more")
    table = []
    for number, (name, chance) in enumerate(zip(names, chances, strict=True)):
        ended = (size >= edges[number]) & (size < edges[number + 1])
        table.append(
            {
                "class": name,
                "alerts": int(ended.sum()),
                "expected_alerts": round(float(chance.sum()), 1),
                "observed_to_expected": share(ended.sum(), chance.sum()),
                "wrong_sequence_alerts": wrong,
            }
        )
    return table


def percentage_table(by_year: dict[int, list[dict]]) -> list[dict]:
    """Return, for each model, the three conditions of a percentage for the scored years.

    `by_year` has the table `risk_recalibrated` of each scored year. Each model has one row for
    its values after the recalibration and one row for its values before it. A model can give
    a percentage if the three conditions are true (`docs/method.md` section 11.21).
    """
    found: dict[tuple, dict] = {}
    for rows in by_year.values():
        for row in rows:
            if row["group"] != "all":
                continue
            for values, end in (("recalibrated", ""), ("before", "_before")):
                model = found.setdefault((row["moment_h"], row["limit_ha"], values), _empty())
                model["skill"].append(row[f"brier_skill{end}"])
                model["level"].append(row[f"observed_to_expected{end}"])
                model["large"] += row["large"]
                model["expected"] += row[f"expected_large{end}"]
    return [
        {"moment_h": moment, "limit_ha": limit, "values": values} | _conditions(model)
        for (moment, limit, values), model in found.items()
    ]


def _empty() -> dict:
    return {"skill": [], "level": [], "large": 0, "expected": 0.0}


def answer_table(rows: list[dict]) -> list[dict]:
    """Return, for each model, the answer of the test year (`docs/method.md` section 11.25).

    `rows` is the table `risk_recalibrated` of the test year. A model holds its percentage if
    it has enough large alerts, a Brier skill score of more than 0, and a level in the range
    of one year. With too few large alerts the model has no answer.
    """
    low, high = config.RISK_LEVEL_YEAR
    table = []
    for row in rows:
        if row["group"] != "all":
            continue
        enough = row["large"] >= config.RISK_TEST_MIN_LARGE
        better = row["brier_skill"] is not None and row["brier_skill"] > 0
        level = row["observed_to_expected"]
        in_range = level is not None and low <= level <= high
        names = ("moment_h", "limit_ha", "alerts", "large", "auc", "brier_skill")
        table.append(
            {name: row[name] for name in names}
            | {
                "observed_to_expected": level,
                "enough_large_alerts": enough,
                "better_than_base_rate": better,
                "level_in_range": in_range,
                "percentage_holds": (better and in_range) if enough else None,
            }
        )
    return table


def _conditions(model: dict) -> dict:
    low, high = config.RISK_LEVEL_YEAR
    all_low, all_high = config.RISK_LEVEL_ALL
    level_all = share(model["large"], model["expected"])
    better = all(skill is not None and skill > 0 for skill in model["skill"])
    together = level_all is not None and all_low <= level_all <= all_high
    each = all(level is not None and low <= level <= high for level in model["level"])
    return {
        "years": len(model["level"]),
        # A model with no large alert in a year has no skill value for that year.
        "brier_skill_smallest": min((s for s in model["skill"] if s is not None), default=None),
        "level_all_years": level_all,
        "level_smallest": min((v for v in model["level"] if v is not None), default=None),
        "level_largest": max((v for v in model["level"] if v is not None), default=None),
        "better_than_base_rate_each_year": better,
        "level_all_years_in_range": together,
        "level_each_year_in_range": each,
        "percentage": better and together and each,
    }
