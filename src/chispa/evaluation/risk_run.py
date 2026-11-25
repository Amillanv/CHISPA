"""One run of the growth risk: the rows of each year, the models of each split and each table.

The numbers of a year come from models of other years. Thus one run makes all years: each table
then has the same rows, the same code and the same configuration, and no file keeps a part.
`docs/method.md` sections 11.21 and 11.22 give the rules.
"""

from pathlib import Path

import numpy as np

from chispa import confidence, config
from chispa.evaluation.confidence import MOMENTS, as_table, year_rows
from chispa.evaluation.risk import (
    all_alerts_table,
    fit_models,
    group_table,
    key,
    measures,
    new_or_none,
    result_table,
    seen_first,
    sized_rows,
    weight_table,
)
from chispa.evaluation.risk_calibration import calibration_table
from chispa.evaluation.risk_inputs import INPUT_SETS, dryness_inputs, dryness_of

Tables = dict[str, list[dict]]
ADOPTED = "inputs now"  # The set of inputs of the models of each table but `risk_inputs`.
COMPARED = ("alerts", "large", "auc", "average_precision", "top_tenth_large")


def year_parts(year: int, store_path: Path, raw_dir: Path) -> dict:
    """Return the rows of one year with their sizes and each candidate input, the areas of its
    fires and its groups."""
    rows, (detections, pairs, fires) = year_rows(year, store_path, raw_dir)
    dryness = dryness_of(detections, raw_dir, year)
    for moment in MOMENTS:
        for row in rows[moment]:
            row["inputs"] |= dryness_inputs(dryness, row.pop("positions"))
    first = seen_first(detections, pairs, fires)
    sized = {moment: sized_rows(rows[moment], first, fires["area_ha"]) for moment in MOMENTS}
    return {"rows": sized, "area_ha": fires["area_ha"], "alerts": group_table(sized, fires)}


def risk_tables(store_path: Path, raw_dir: Path) -> dict[int, Tables]:
    """Return the tables of the growth risk for each year with mapped fires.

    The main tables have models from each other year: a cross-validation by year. The tables
    with `earlier` in the name have models from the years before a year only: a split in time
    sequence. The first year has no earlier year.
    """
    parts = {year: year_parts(year, store_path, raw_dir) for year in config.YEAR_ROLES}
    path = config.RESULTS_DIR / str(config.DEVELOPMENT_YEAR) / "confidence" / "model.json"
    baselines, tables, extra = confidence.load(path), {}, INPUT_SETS[ADOPTED]
    for year, part in parts.items():
        others, earlier = [o for o in parts if o != year], [o for o in parts if o < year]
        kept = {moment: new_or_none(part["rows"][moment]) for moment in MOMENTS}
        models = fit_models(_training(parts, others), extra)
        tables[year] = {
            "risk": result_table(kept, models, baselines),
            "risk_all_alerts": all_alerts_table(part["rows"], part["area_ha"], models, baselines),
            "risk_calibration": calibration_table(kept, models),
            "risk_alerts": part["alerts"],
            "risk_weights": weight_table(models),
            "risk_inputs": input_table(parts, year, kept),
        }
        if earlier:
            models = fit_models(_training(parts, earlier), extra)
            tables[year]["risk_earlier"] = result_table(kept, models, baselines)
            tables[year]["risk_calibration_earlier"] = calibration_table(kept, models)
    return tables


def input_table(parts: dict[int, dict], year: int, kept: dict[str, list]) -> list[dict]:
    """Return the measures of each set of inputs for one year (`docs/method.md` section 11.22).

    The AUC, the average precision and the top tenth have models from each other year. The three
    last columns are the level, with models from the earlier years only.
    """
    others, earlier = [o for o in parts if o != year], [o for o in parts if o < year]
    table = []
    for name, extra in INPUT_SETS.items():
        models = fit_models(_training(parts, others), extra)
        level = (
            calibration_table(kept, fit_models(_training(parts, earlier), extra)) if earlier else []
        )
        level = {(row["moment_h"], row["limit_ha"]): row for row in level if row["group"] == "all"}
        for moment in MOMENTS:
            rows = kept[moment]
            size = np.array([row["size_ha"] for row in rows])
            seen = np.array([row["seen_ha"] for row in rows])
            for limit in config.RISK_LIMITS_HA:
                model = models[key(moment, limit)]
                values = confidence.probability(model, as_table(rows, tuple(model["inputs"]))[0])
                found, at = measures(values, size, seen, limit), level.get((moment, limit), {})
                row = {"inputs": name, "moment_h": moment, "limit_ha": limit}
                row |= {column: found[column] for column in COMPARED}
                row["expected_large_earlier"] = at.get("expected_large")
                row["observed_to_expected_earlier"] = at.get("observed_to_expected")
                row["brier_skill_earlier"] = at.get("brier_skill")
                table.append(row)
    return table


def _training(parts: dict[int, dict], years: list[int]) -> dict[str, list]:
    return {
        moment: [row for year in years for row in new_or_none(parts[year]["rows"][moment])]
        for moment in MOMENTS
    }
