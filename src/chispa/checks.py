"""The commands that check a part of a stage: burn, images, visibility, growth and severity.

Each command makes its result tables and the summary again. They are not in `cli.py`,
which has the commands that get data, make the store and make the events.
`project` gives the Earth Engine project only when a command needs it.
"""

from collections.abc import Callable
from datetime import UTC, datetime

from chispa import config, risk_live
from chispa.evaluation import (
    advance,
    burn,
    candidates,
    curve,
    flames,
    front_alerts,
    fronts,
    images,
    joined,
    pixels,
)
from chispa.evaluation.confidence import confidence_tables
from chispa.evaluation.confidence_curve import curve_tables
from chispa.evaluation.events import events_with_a_match
from chispa.evaluation.growth import step_rows
from chispa.evaluation.report import write_summary, write_tables
from chispa.evaluation.risk_run import risk_tables
from chispa.evaluation.risk_save import refresh
from chispa.evaluation.run import prepare
from chispa.evaluation.severity import severity_tables
from chispa.evaluation.visibility import month_table, visibility
from chispa.sources import scars


def run_table(name: str, year: int) -> None:
    """Make the tables of one check of one fused year: visibility, growth or severity."""
    if name == "severity" and year == config.TEST_YEAR and config.SEVERITY_POWER_STEPS_MW is None:
        raise SystemExit(
            f"{year} is the test year. Set the severity steps on {config.DEVELOPMENT_YEAR} first."
        )
    arguments = (year, config.STORE_PATH, config.RAW_DIR)
    if name == "severity":
        tables = severity_tables(*arguments)
    elif name == "confidence":
        # A year with no map of burn scars has only the table against the burn curve.
        tables = confidence_tables(*arguments) if year in config.YEAR_ROLES else {}
        curves = config.DATA_DIR / "curves" / f"{year}_days.csv"
        if curves.exists():
            tables |= curve_tables(*arguments, curve.last_answers(curves))
        if not tables:
            raise SystemExit(f"Run `chispa curve --year {year} --events` first.")
    elif name == "growth":
        tables = {"growth_steps": step_rows(*arguments)}
    elif name == "fronts":
        tables = fronts.step_tables(*arguments) | {"front_alerts": front_alerts.table(*arguments)}
    else:
        tables = {
            "visibility": visibility(*arguments),
            "visibility_months": month_table(year, config.RAW_DIR),
        }
    write_tables(tables, year, config.RESULTS_DIR)
    write_summary(config.RESULTS_DIR)
    print(f"{year}: see results/SUMMARY.md, tables {', '.join(tables)}.")


def run_risk(test_run: bool) -> None:
    """Make the growth risk tables of each year with mapped fires, in one run.

    The numbers of a year come from models of the other years. Thus one run makes all years:
    each table then has the same rows, the same code and the same configuration.
    A test run also makes the tables of the test year, with fires from the Monitor map.
    """
    tables = risk_tables(config.STORE_PATH, config.RAW_DIR, test_run)
    for year, of_year in tables.items():
        write_tables(of_year, year, config.RESULTS_DIR)
    write_summary(config.RESULTS_DIR)
    names = ", ".join(tables[max(tables)])  # The first year has no table of the earlier years.
    print(f"{min(tables)} to {max(tables)}: see results/SUMMARY.md, tables {names}.")


def update_risk(project: str | None) -> str:
    """Make the growth risk of each alert with a new moment, and return one line.

    This is a step of `chispa update`. It first makes the saved models and outcomes again if
    they are absent, or if the Monitor map has a new month: that needs the evaluation, and the
    live path does not import it. With no project of Earth Engine it gets no file.
    """
    now = datetime.now(UTC)
    return risk_live.update(config.STORE_PATH, config.RAW_DIR, now, (project, refresh))


def run_burn(year: int, project: Callable[[], str]) -> None:
    """Make the burn check of one fused year: the targets, their measures and the table.

    The first run makes the targets. A later run keeps them and measures only what is absent.
    """
    if year == config.TEST_YEAR and config.BURN_DNBR_MIN is None:
        raise SystemExit(
            f"{year} is the test year. Set BURN_DNBR_MIN on {config.DEVELOPMENT_YEAR} first."
        )
    folder = config.RESULTS_DIR / str(year) / "burn_check"
    if not (folder / "targets.csv").exists():
        burn.write(
            folder / "targets.csv", burn.make_targets(year, config.STORE_PATH, config.RAW_DIR)
        )
    scars.check_access(project())
    targets = burn.read(folder / "targets.csv")
    burn.measure(targets, folder / "measures.csv")
    all_pairs = year == config.DEVELOPMENT_YEAR
    measures = burn.read(folder / "measures.csv")
    tables = {"burn_check": burn.table(targets, measures, all_pairs)}
    if config.BURN_DNBR_MIN is not None:
        tables["burn_rule"] = burn.rule_table(targets, measures)
    write_tables(tables, year, config.RESULTS_DIR)
    write_summary(config.RESULTS_DIR)
    print(f"{year}: {len(targets)} boxes measured. See results/SUMMARY.md, table burn_check.")


def run_candidates(year: int, project: Callable[[], str]) -> None:
    """Measure each candidate for the burned ground on the boxes of the burn check."""
    targets_path = config.RESULTS_DIR / str(year) / "burn_check" / "targets.csv"
    if not targets_path.exists():
        raise SystemExit(f"Run `chispa burn --year {year}` first.")
    development = year == config.DEVELOPMENT_YEAR
    if not development and config.BURN_CANDIDATES is None:
        raise SystemExit(f"Set BURN_CANDIDATES on {config.DEVELOPMENT_YEAR} first.")
    look = config.RESULTS_DIR / str(year) / "image_check_2"
    has_look = (look / "sample.csv").exists()
    if year == config.PART_TEST_YEAR and not has_look:
        raise SystemExit(f"Run `chispa images --year {year} --test-run --look 2` first.")
    # A person must not see an answer of a candidate before the answers of the person are complete.
    if has_look and any(row[2] not in images.ANSWERS for row in images.read_answers(look)):
        raise SystemExit(f"{look / 'answers.csv'} has a chip with no answer. Complete it first.")
    scars.check_access(project())
    targets = burn.read(targets_path)
    path = config.RESULTS_DIR / str(year) / "burn_candidates" / "measures.csv"
    candidates.measure(targets, path)
    tables = {"burn_candidates": candidates.table(targets, burn.read(path), development)}
    if has_look and config.BURN_CANDIDATES is not None:
        answers, apart = images.read_answers(look), images.later_only(look)
        tables["burn_candidates_person"] = candidates.person_table(answers, burn.read(path), apart)
    write_tables(tables, year, config.RESULTS_DIR)
    write_summary(config.RESULTS_DIR)
    print(f"{year}: {len(targets)} boxes measured. See results/SUMMARY.md, table burn_candidates.")


def run_advance(year: int, project: Callable[[], str]) -> None:
    """Compare the advance of VIIRS with the new burned ground, for the long events of a year."""
    scars.check_access(project())
    targets, viirs = advance.long_events(year, config.STORE_PATH, config.RAW_DIR)
    path = config.RESULTS_DIR / str(year) / "advance_check" / "events.csv"
    advance.measure(targets, viirs, path)
    write_tables({"advance_check": advance.table(burn.read(path))}, year, config.RESULTS_DIR)
    write_summary(config.RESULTS_DIR)
    print(f"{year}: {len(targets)} events. See results/SUMMARY.md, table advance_check.")


def run_flames(year: int, project: Callable[[], str]) -> None:
    """Compare the answers of the fronts of a year with the flames in Sentinel-2 images."""
    scars.check_access(project())
    path = config.RESULTS_DIR / str(year) / "front_flames" / "fronts.csv"
    flames.measure(year, config.STORE_PATH, config.RAW_DIR, path)
    write_tables({"front_flames": flames.table(burn.read(path))}, year, config.RESULTS_DIR)
    write_summary(config.RESULTS_DIR)
    print(f"{year}: see results/SUMMARY.md, table front_flames.")


def run_pixels(year: int, project: Callable[[], str]) -> None:
    """Compare the burned pixels of the selected rule with the map, in each box."""
    folder = config.RESULTS_DIR / str(year)
    scars.check_access(project())
    targets = burn.read(folder / "burn_check" / "targets.csv")
    path = folder / "burn_pixels" / "areas.csv"
    pixels.measure(targets, path)
    write_tables({"burn_pixels": pixels.table(targets, burn.read(path))}, year, config.RESULTS_DIR)
    write_summary(config.RESULTS_DIR)
    print(f"{year}: {len(targets)} boxes. See results/SUMMARY.md, table burn_pixels.")


def run_event_curves(year: int, project: Callable[[], str]) -> None:
    """Measure the burn curve of each event of a year in the biome, and make its table.

    The curves are large files. They are in the data folder, as the store. A year needs no map.
    """
    scars.check_access(project())
    folder = config.DATA_DIR / "curves"
    targets = curve.event_targets(year, config.STORE_PATH, config.RAW_DIR, datetime.now(UTC))
    burn.write(folder / f"{year}_events.csv", targets)
    if year not in config.YEAR_ROLES:
        # The events of the year in progress can change: a later detection can merge two events.
        # An old curve can thus be of a different box. Each run measures all its events again.
        (folder / f"{year}_days.csv").unlink(missing_ok=True)
    curve.measure(targets, folder / f"{year}_days.csv")
    rows = burn.read(folder / f"{year}_days.csv")
    tables = {"burn_curve_events": curve.table(targets, rows)}
    if year in config.YEAR_ROLES:
        # A year with a map of burn scars: the curve against the match of each event.
        detections, pairs, _, _ = prepare(year, config.STORE_PATH, config.RAW_DIR)
        matched = events_with_a_match(detections, pairs)
        tables["burn_curve_map"] = curve.map_table(targets, rows, matched)
    write_tables(tables, year, config.RESULTS_DIR)
    write_summary(config.RESULTS_DIR)
    print(f"{year}: {len(targets)} events. See results/SUMMARY.md, table burn_curve_events.")


def run_curve(year: int, project: Callable[[], str]) -> None:
    """Measure the burn curve of each box of the burn check, and make its tables."""
    folder = config.RESULTS_DIR / str(year)
    other = folder / "burn_candidates" / "measures.csv"
    if not other.exists():
        raise SystemExit(f"Run `chispa candidates --year {year}` first.")
    scars.check_access(project())
    targets = burn.read(folder / "burn_check" / "targets.csv")
    path = folder / "burn_curve" / "days.csv"
    curve.measure(targets, path)
    rows = burn.read(path)
    tables = {"burn_curve": curve.table(targets, rows)}
    tables["burn_curve_check"] = curve.check_table(targets, rows, burn.read(other))
    # The first definition of the curve failed. Its table is a result as each other table.
    joined.measure(targets, folder / "burn_curve" / "joined.csv")
    first = burn.read(folder / "burn_curve" / "joined.csv")
    tables["burn_curve_joined"] = joined.table(targets, first, rows)
    write_tables(tables, year, config.RESULTS_DIR)
    write_summary(config.RESULTS_DIR)
    print(f"{year}: {len(targets)} boxes. See results/SUMMARY.md, table burn_curve.")


def run_images(year: int, project: Callable[[], str], look: int) -> None:
    """Make the pictures of the image check, then count the answers of the person.

    The first run makes the sample from the targets of the burn check. A later run keeps it.
    The second look has the events of the first look again and boxes with no fire.
    A look with no answer makes no table: a table of empty answers is not a result.
    """
    burn_folder = config.RESULTS_DIR / str(year) / "burn_check"
    first_folder = config.RESULTS_DIR / str(year) / "image_check"
    mark = "" if look == 1 else f"_{look}"
    folder, pictures = (
        first_folder.with_name(f"image_check{mark}"),
        config.IMAGE_DIR / f"{year}{mark}",
    )
    if not (burn_folder / "measures.csv").exists():
        raise SystemExit(f"Run `chispa burn --year {year}` first.")
    if not (folder / "sample.csv").exists():
        scars.check_access(project())
        targets = burn.read(burn_folder / "targets.csv")
        if look == 1:
            sample, key = images.draw(targets)
            images.get_pictures(sample, pictures)
        else:
            first_key = first_folder / "key.csv"
            first_look = burn.read(first_key) if first_key.exists() else []
            sample, key = images.draw_second(targets, first_look)
            images.get_views(sample, pictures)
        images.write_sample(folder, sample, key)
        print(f"{year}: {len(sample)} chips. The pictures are in {pictures}.")
        print(f"Write one answer for each chip in {folder / 'answers.csv'}: {images.ANSWERS}.")
    answers = images.read_answers(folder)
    if look == 2:
        # The person saw an opinion on these events before the second look.
        answers = [row for row in answers if row[0] not in config.IMAGE_NOT_BLIND]
    if not any(answer for _, _, answer in answers):
        print(f"{year}: {folder / 'answers.csv'} has no answer. No table is made.")
        return
    tables = {f"image_check{mark}": images.count(answers)}
    if config.BURN_DNBR_MIN is not None:
        measures = burn.read(burn_folder / "measures.csv")
        tables[f"image_agreement{mark}"] = images.agreement(answers, measures)
    write_tables(tables, year, config.RESULTS_DIR)
    write_summary(config.RESULTS_DIR)
