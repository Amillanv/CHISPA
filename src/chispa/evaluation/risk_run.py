"""One run of the growth risk: the rows of each year, the models of each split and each table.

The numbers of a year come from models of other years. Thus one run makes all years: each table
then has the same rows, the same code and the same configuration, and no file keeps a part.
`docs/method.md` sections 11.21 and 11.22 give the rules.
"""

from datetime import UTC, date, datetime
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
from chispa.evaluation.risk_calibration import calibration_table, source_table
from chispa.evaluation.risk_inputs import (
    INPUT_SETS,
    add_model_inputs,
    dryness_inputs,
    dryness_of,
    river_inputs,
)
from chispa.evaluation.risk_mark import mark_table, no_mark, with_mark
from chispa.evaluation.risk_parity import parity_table
from chispa.evaluation.risk_recalibration import recalibration_tables
from chispa.evaluation.risk_rule import NOW, rule_table
from chispa.evaluation.risk_test import monitor_part, replay_table
from chispa.sources import river

Tables = dict[str, list[dict]]
COMPARED = ("alerts", "large", "auc", "average_precision", "top_tenth_large")


def year_parts(year: int, store_path: Path, raw_dir: Path) -> dict:
    """Return the rows of one year with their sizes and each candidate input, the areas of its
    fires and its groups."""
    rows, (detections, pairs, fires) = year_rows(year, store_path, raw_dir)
    dryness = dryness_of(detections, raw_dir, year)
    levels = river.read_days(raw_dir, year - 1, year)
    for moment in MOMENTS:
        add_model_inputs(rows[moment], detections, raw_dir, year, date(year + 1, 1, 10))
        for row in rows[moment]:
            # The inputs of the groups that the table `risk_inputs` examines, and no model has.
            row["inputs"] |= dryness_inputs(dryness, row.pop("positions"))
            row["inputs"] |= river_inputs(levels, datetime.fromtimestamp(row["at"], UTC).date())
    first = seen_first(detections, pairs, fires)
    sized = {moment: sized_rows(rows[moment], first, fires["area_ha"]) for moment in MOMENTS}
    return {"rows": sized, "area_ha": fires["area_ha"], "alerts": group_table(sized, fires)}


def risk_tables(store_path: Path, raw_dir: Path, test_run: bool = False) -> dict[int, Tables]:
    """Return the tables of the growth risk for each year with mapped fires.

    The main tables have models from each other year: a cross-validation by year. The tables
    with `earlier` in the name have models from the years before a year only: a split in time
    sequence. The first year has no earlier year. A test run adds the tables of the test year.
    """
    parts = {year: year_parts(year, store_path, raw_dir) for year in config.YEAR_ROLES}
    path = config.RESULTS_DIR / str(config.DEVELOPMENT_YEAR) / "confidence" / "model.json"
    baselines, tables, change = confidence.load(path), {}, INPUT_SETS[NOW]
    of_earlier, levels = {}, set_levels(parts)
    for year, part in parts.items():
        others, earlier = [o for o in parts if o != year], [o for o in parts if o < year]
        kept = {moment: new_or_none(part["rows"][moment]) for moment in MOMENTS}
        models = fit_models(_training(parts, others), *change)
        tables[year] = {
            "risk": result_table(kept, models, baselines),
            "risk_all_alerts": all_alerts_table(part["rows"], part["area_ha"], models, baselines),
            "risk_calibration": calibration_table(kept, models),
            "risk_alerts": part["alerts"],
            "risk_mark": mark_table(part["rows"]),
            "risk_weights": weight_table(models),
            "risk_inputs": with_levels(
                input_table(parts, year, kept, tuple(INPUT_SETS)), levels, year
            ),
        }
        if earlier:
            # The models of the earlier years also have the limits of the percentage.
            limits = tuple(sorted({*config.RISK_LIMITS_HA, *config.RISK_CLASS_LIMITS_HA}))
            models = of_earlier[year] = fit_models(_training(parts, earlier), *change, limits)
            tables[year]["risk_earlier"] = result_table(kept, models, baselines)
            tables[year]["risk_calibration_earlier"] = calibration_table(kept, models)
            tables[year]["risk_level_sources"] = source_table(kept, models)
    _add_shared_tables(parts, of_earlier, tables)
    if test_run:
        tables[config.RISK_TEST_YEAR] = _test_tables(parts, of_earlier, (store_path, raw_dir))
    return tables


def _add_shared_tables(parts: dict, of_earlier: dict, tables: dict[int, Tables]) -> None:
    """Add the tables that need all years: the rule, the new fires and the recalibration."""
    # The rule for a group of inputs is for all years together: its table is with the newest year.
    removes = {name for name in INPUT_SETS if name.startswith("without ")}
    by_year = {year: found["risk_inputs"] for year, found in tables.items()}
    tables[max(tables)]["risk_input_rule"] = rule_table(by_year, removes)
    for more in (fire_tables(parts), recalibration_tables(parts, of_earlier)):
        for year, found in more.items():
            tables[year] |= found
    # The conditions of a percentage with the mark that a live alert has, and with no mark
    # (section 11.35).
    for name, change in (("mark", with_mark), ("no_mark", no_mark)):
        changed = {year: part | {"rows": change(part["rows"])} for year, part in parts.items()}
        found = recalibration_tables(changed, of_earlier)
        tables[max(found)][f"risk_percentage_{name}"] = found[max(found)]["risk_percentage"]


def _test_tables(parts: dict, of_earlier: dict, paths: tuple[Path, Path]) -> Tables:
    """Return the tables of the test year, with the check of the live path against its rows.

    The check reads each alert of the test through the live path, and no outcome (section 11.35).
    """
    part = monitor_part(config.RISK_TEST_YEAR, *paths)
    models = of_earlier[max(of_earlier)]
    names = {m: models[key(m, config.RISK_CLASS_LIMITS_HA[0])]["inputs"] for m in MOMENTS}
    tables = tables_of_test_year(parts, of_earlier, part)
    return tables | {"risk_live_inputs": parity_table(part["rows"], names, paths)}


def tables_of_test_year(parts: dict[int, dict], of_earlier: dict[int, dict], part: dict) -> Tables:
    """Return the tables of the test year (`docs/method.md` section 11.25).

    The models get their weights from each year with an annual map, and they are scored one
    time on the alerts of the test year: `part` has their rows, with sizes from the Monitor map.
    """
    year = config.RISK_TEST_YEAR
    limits = tuple(sorted({*config.RISK_LIMITS_HA, *config.RISK_CLASS_LIMITS_HA}))
    models = fit_models(_training(parts, sorted(parts)), *INPUT_SETS[NOW], limits)
    path = config.RESULTS_DIR / str(config.DEVELOPMENT_YEAR) / "confidence" / "model.json"
    kept = {moment: new_or_none(part["rows"][moment]) for moment in MOMENTS}
    tables = {"risk": result_table(kept, models, confidence.load(path))}
    with_test, all_models = parts | {year: part}, of_earlier | {year: models}
    found = recalibration_tables(with_test, all_models, year)
    tables |= {"risk_mark": mark_table(part["rows"])}
    tables |= {"risk_replay_mark": replay_table(with_test, all_models, year, mark=True)}
    return tables | found[year] | {"risk_replay": replay_table(with_test, all_models, year)}


def fire_tables(parts: dict[int, dict]) -> dict[int, Tables]:
    """Return the tables for the alerts with a new fire only (`docs/method.md` section 11.23).

    The question is: if an alert has a new fire, does that fire become large? The models get
    their weights from the alerts with a new fire, and the tables measure them on those alerts.
    """
    fires = {}
    for year, part in parts.items():
        rows = {
            m: [row for row in new_or_none(part["rows"][m]) if row["size_ha"] > 0] for m in MOMENTS
        }
        fires[year] = {"rows": rows}
    tables = {}
    for year, part in fires.items():
        earlier = [other for other in fires if other < year]
        tables[year] = {"risk_fire": input_table(fires, year, part["rows"], (NOW,))}
        if earlier:
            models = fit_models(_training(fires, earlier), *INPUT_SETS[NOW])
            tables[year]["risk_fire_calibration"] = calibration_table(part["rows"], models)
    return tables


def input_table(parts: dict[int, dict], year: int, kept: dict[str, list], names: tuple) -> list:
    """Return the measures of each named set of inputs for one year.

    `docs/method.md` section 11.22 gives the sets. The AUC, the average precision and the top
    tenth have models from each other year: a cross-validation by year.
    """
    others = [o for o in parts if o != year]
    table = []
    for name in names:
        models = fit_models(_training(parts, others), *INPUT_SETS[name])
        for moment in MOMENTS:
            rows = kept[moment]
            size = np.array([row["size_ha"] for row in rows])
            seen = np.array([row["seen_ha"] for row in rows])
            for limit in config.RISK_LIMITS_HA:
                model = models[key(moment, limit)]
                values = confidence.probability(model, as_table(rows, tuple(model["inputs"]))[0])
                found = measures(values, size, seen, limit)
                row = {"inputs": name, "moment_h": moment, "limit_ha": limit}
                table.append(row | {column: found[column] for column in COMPARED})
    return table


def set_levels(parts: dict[int, dict]) -> dict[tuple, dict]:
    """Return the level of each set of inputs after the recalibration, for each scored year.

    The rule for a group of inputs reads this level (`docs/method.md` section 11.22). A key
    has the set, the year, the moment and the limit.
    """
    limits = tuple(sorted({*config.RISK_LIMITS_HA, *config.RISK_CLASS_LIMITS_HA}))
    found = {}
    for name, change in INPUT_SETS.items():
        models = {}
        for year in parts:
            earlier = [other for other in parts if other < year]
            if earlier:
                models[year] = fit_models(_training(parts, earlier), *change, limits)
        for year, tables in recalibration_tables(parts, models).items():
            for row in tables["risk_recalibrated"]:
                if row["group"] == "all":
                    found[(name, year, row["moment_h"], row["limit_ha"])] = row
    return found


def with_levels(table: list[dict], levels: dict[tuple, dict], year: int) -> list[dict]:
    """Return the rows of the table `risk_inputs` with the level of their set of inputs.

    The level is that after the recalibration. A year that is not scored has no level.
    """
    names = ("large", "expected_large", "observed_to_expected", "brier_skill")
    rows = []
    for row in table:
        level = levels.get((row["inputs"], year, row["moment_h"], row["limit_ha"]), {})
        rows.append(row | {f"recalibrated_{name}": level.get(name) for name in names})
    return rows


def _training(parts: dict[int, dict], years: list[int]) -> dict[str, list]:
    return {
        moment: [row for year in years for row in new_or_none(parts[year]["rows"][moment])]
        for moment in MOMENTS
    }
