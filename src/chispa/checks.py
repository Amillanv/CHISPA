"""The commands that check a part of a stage: burn, images, visibility, growth and severity.

Each command makes its result tables and the summary again. They are not in `cli.py`,
which has the commands that get data, make the store and make the events.
`project` gives the Earth Engine project only when a command needs it.
"""

from collections.abc import Callable

from chispa import config
from chispa.evaluation import burn, candidates, images
from chispa.evaluation.confidence import confidence_tables
from chispa.evaluation.growth import step_rows
from chispa.evaluation.report import write_summary, write_tables
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
        tables = confidence_tables(*arguments)
    elif name == "growth":
        tables = {"growth_steps": step_rows(*arguments)}
    else:
        tables = {
            "visibility": visibility(*arguments),
            "visibility_months": month_table(year, config.RAW_DIR),
        }
    write_tables(tables, year, config.RESULTS_DIR)
    write_summary(config.RESULTS_DIR)
    print(f"{year}: see results/SUMMARY.md, tables {', '.join(tables)}.")


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
    scars.check_access(project())
    targets = burn.read(targets_path)
    path = config.RESULTS_DIR / str(year) / "burn_candidates" / "measures.csv"
    candidates.measure(targets, path)
    tables = {"burn_candidates": candidates.table(targets, burn.read(path), development)}
    look = config.RESULTS_DIR / str(year) / "image_check_2"
    if (look / "answers.csv").exists() and config.BURN_CANDIDATES is not None:
        answers = images.read_answers(look)
        tables["burn_candidates_person"] = candidates.person_table(answers, burn.read(path))
    write_tables(tables, year, config.RESULTS_DIR)
    write_summary(config.RESULTS_DIR)
    print(f"{year}: {len(targets)} boxes measured. See results/SUMMARY.md, table burn_candidates.")


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
    if not any(answer for _, _, answer in answers):
        print(f"{year}: {folder / 'answers.csv'} has no answer. No table is made.")
        return
    tables = {f"image_check{mark}": images.count(answers)}
    if config.BURN_DNBR_MIN is not None:
        measures = burn.read(burn_folder / "measures.csv")
        tables[f"image_agreement{mark}"] = images.agreement(answers, measures)
    write_tables(tables, year, config.RESULTS_DIR)
    write_summary(config.RESULTS_DIR)
