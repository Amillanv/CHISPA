"""The command line: one entry point for each step of the work.

One command for each step lets a reader make each result again.
"""

import argparse
import os
from datetime import UTC, datetime

from dotenv import load_dotenv

from chispa import bucket, config, live
from chispa.build import build_store
from chispa.evaluation import burn, images
from chispa.evaluation.growth import step_rows
from chispa.evaluation.report import write_summary, write_tables
from chispa.evaluation.run import evaluate
from chispa.evaluation.severity import severity_tables
from chispa.evaluation.visibility import visibility
from chispa.fusion import LEVELS, fuse
from chispa.grid import layer_grid, pantanal_grid
from chispa.sources import (
    border,
    burnday,
    firms,
    goes,
    inpe,
    landcover,
    passes,
    protected,
    scars,
    settlements,
)
from chispa.store import open_store, read_detections, replace_fusion

YEAR_SOURCES = ("firms", "goes", "goes_mask", "inpe", "passes", "scars", "burnday", "landcover")
FIXED_SOURCES = ("border", "protected", "settlements")
NOT_BUILT = {
    "serve": "Start the dashboard.",
    "mcp": "Start the MCP server.",
    "grade": "Run the gold questions and grade the answers.",
}


def main(arguments: list[str] | None = None) -> None:
    """Read the command and run it."""
    parser = argparse.ArgumentParser(prog="chispa", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="Do a check of the keys and the logins.")
    fetch = commands.add_parser("fetch", help="Get the raw files of one source for one year.")
    fetch.add_argument(
        "source",
        choices=[*YEAR_SOURCES, *FIXED_SOURCES],
    )
    fetch.add_argument("--year", type=int, help="Necessary for a source that has years.")
    fetch.add_argument("--push", action="store_true", help="Also copy new files to the bucket.")
    build = commands.add_parser("build", help="Make the store from the raw files.")
    build.add_argument("--offline", action="store_true", help="Do not get files from the bucket.")
    fusion = commands.add_parser("fuse", help="Replay one year of detections into events.")
    fusion.add_argument("--year", type=int, required=True)
    evaluation = commands.add_parser("evaluate", help="Compare one fused year with the fires.")
    evaluation.add_argument("--year", type=int, required=True)
    evaluation.add_argument("--test-run", action="store_true", help="Permit the test year.")
    checks = {"burn": "burn check", "images": "image check", "visibility": "visibility table"}
    for name, text in (checks | {"growth": "growth table", "severity": "severity tables"}).items():
        check = commands.add_parser(name, help=f"Make the {text} of one fused year.")
        check.add_argument("--year", type=int, required=True)
    poll = commands.add_parser("poll", help="Do one pass of the live poller.")
    poll.add_argument("--push", action="store_true", help="Also copy complete logs to the bucket.")
    for name, text in NOT_BUILT.items():
        commands.add_parser(name, help=f"{text} Not built.")
    chosen = parser.parse_args(arguments)
    load_dotenv()
    if chosen.command == "check":
        check()
    elif chosen.command == "fetch":
        run_fetch(chosen.source, chosen.year, chosen.push)
    elif chosen.command == "build":
        run_build(chosen.offline)
    elif chosen.command == "fuse":
        run_fuse(chosen.year)
    elif chosen.command == "evaluate":
        run_evaluate(chosen.year, chosen.test_run)
    elif chosen.command == "burn":
        run_burn(chosen.year)
    elif chosen.command in ("visibility", "growth", "severity"):
        run_table(chosen.command, chosen.year)
    elif chosen.command == "images":
        run_images(chosen.year)
    elif chosen.command == "poll":
        run_poll(chosen.push)
    else:
        parser.exit(1, f"The command '{chosen.command}' is not built.\n")


def read_setting(name: str) -> str:
    """Return a value from the environment, or stop with an instruction."""
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} is not set. Add it to the file .env. README.md gives the setup.")
    return value


def check() -> None:
    """Show if each external access works."""
    print(f"Bucket: public read works. {len(bucket.list_objects())} raw files.")
    status = firms.key_status(read_setting("FIRMS_API_KEY"))
    used, limit = status["current_transactions"], status["transaction_limit"]
    print(f"FIRMS: key works. {used} of {limit} transactions used.")
    bands = scars.check_access(read_setting("EE_PROJECT"))
    print(f"Earth Engine: login works. Found {', '.join(bands)}.")


def run_fetch(source: str, year: int | None, push: bool) -> None:
    """Download the raw files of one source from its origin. This does not change the store."""
    if source in YEAR_SOURCES and year is None:
        raise SystemExit("Give the year: --year 2024.")
    if source == "firms":
        files = firms.download_year(year, read_setting("FIRMS_API_KEY"), config.RAW_DIR)
    elif source == "inpe":
        files = inpe.download_year(year, config.RAW_DIR)
    elif source == "landcover":
        files = landcover.download_year(
            year, read_setting("EE_PROJECT"), config.RAW_DIR, layer_grid()
        )
    elif source == "protected":
        files = protected.download(read_setting("EE_PROJECT"), config.RAW_DIR, layer_grid())
    elif source == "settlements":
        files = settlements.download(read_setting("EE_PROJECT"), config.RAW_DIR, layer_grid())
    elif source == "passes":
        files = passes.download_year(year, config.RAW_DIR)
    elif source == "goes_mask":
        files = goes.download_masks(year, config.RAW_DIR)
    elif source == "scars":
        project = read_setting("EE_PROJECT")
        files = scars.download_year(year, project, config.RAW_DIR, pantanal_grid())
    elif source == "burnday":
        files = burnday.download_year(year, read_setting("EE_PROJECT"), config.RAW_DIR)
    elif source == "border":
        files = [border.download(config.RAW_DIR)]
    elif year == config.GOES_GAP_START.year:
        files = goes.download_gap(config.RAW_DIR)
    else:
        raise SystemExit(f"FIRMS has no known GOES gap in {year}. There is nothing to get.")
    print(f"{source}: {len(files)} raw files are on disk.")
    if push:
        new_files = bucket.push(config.RAW_DIR, bucket.source_files(config.RAW_DIR, source))
        print(f"{source}: {new_files} new files copied to the bucket.")


def run_build(offline: bool) -> None:
    """Get absent raw files from the bucket, then make the store again."""
    if not offline:
        print(f"Bucket: {bucket.pull(config.RAW_DIR)} files downloaded.")
    for source, (files, detections, rejected) in build_store(
        config.RAW_DIR, config.STORE_PATH
    ).items():
        print(f"{source}: {files} files, {detections} records, {rejected} rows rejected.")


def run_fuse(year: int) -> None:
    """Replay the detections that became available in one year and save the events."""
    store = open_store(config.STORE_PATH)
    start, end = datetime(year, 1, 1, tzinfo=UTC), datetime(year + 1, 1, 1, tzinfo=UTC)
    # An event id is the year, then a number. Thus the ids of two years do not collide.
    first_id = year * 10_000_000
    events, alerts, memberships = fuse(read_detections(store, start, end), first_id)
    replace_fusion(store, (first_id, first_id + 10_000_000), events, alerts, memberships)
    levels = {level: sum(event.level == level for event in events) for level in LEVELS}
    print(f"{year}: {len(memberships)} detections, {len(events)} events, {levels}.")


def run_evaluate(year: int, test_run: bool) -> None:
    """Write the result tables of one year. The test year needs a clear decision."""
    if year == config.TEST_YEAR and not test_run:
        raise SystemExit(
            f"{year} is the test year. Freeze the configuration first, then add --test-run."
        )
    write_tables(evaluate(year, config.STORE_PATH, config.RAW_DIR), year, config.RESULTS_DIR)
    write_summary(config.RESULTS_DIR)
    print(f"{year}: the tables are in {config.RESULTS_DIR / str(year)}. See results/SUMMARY.md.")


def run_table(name: str, year: int) -> None:
    """Make the tables of one check of one fused year: visibility, growth or severity."""
    if name == "severity" and year == config.TEST_YEAR and config.SEVERITY_POWER_STEPS_MW is None:
        raise SystemExit(
            f"{year} is the test year. Set the severity steps on {config.DEVELOPMENT_YEAR} first."
        )
    arguments = (year, config.STORE_PATH, config.RAW_DIR)
    if name == "severity":
        tables = severity_tables(*arguments)
    elif name == "growth":
        tables = {"growth_steps": step_rows(*arguments)}
    else:
        tables = {"visibility": visibility(*arguments)}
    write_tables(tables, year, config.RESULTS_DIR)
    write_summary(config.RESULTS_DIR)
    print(f"{year}: see results/SUMMARY.md, tables {', '.join(tables)}.")


def run_burn(year: int) -> None:
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
    scars.check_access(read_setting("EE_PROJECT"))
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


def run_images(year: int) -> None:
    """Make the pictures of the image check, then count the answers of the person.

    The first run makes the sample from the targets of the burn check. A later run keeps it.
    """
    burn_folder = config.RESULTS_DIR / str(year) / "burn_check"
    folder = config.RESULTS_DIR / str(year) / "image_check"
    if not (burn_folder / "measures.csv").exists():
        raise SystemExit(f"Run `chispa burn --year {year}` first.")
    if not (folder / "sample.csv").exists():
        scars.check_access(read_setting("EE_PROJECT"))
        sample, key = images.draw(burn.read(burn_folder / "targets.csv"))
        images.get_pictures(sample, config.IMAGE_DIR / str(year))
        images.write_sample(folder, sample, key)
        print(f"{year}: {len(sample)} events. The pictures are in {config.IMAGE_DIR / str(year)}.")
        print(f"Write one answer for each chip in {folder / 'answers.csv'}: {images.ANSWERS}.")
    answers = images.read_answers(folder)
    tables = {"image_check": images.count(answers)}
    if config.BURN_DNBR_MIN is not None:
        measures = burn.read(burn_folder / "measures.csv")
        tables["image_agreement"] = images.agreement(answers, measures)
    write_tables(tables, year, config.RESULTS_DIR)
    write_summary(config.RESULTS_DIR)


def run_poll(push: bool) -> None:
    """Do one pass of the live poller, then update the store and the events of this year."""
    now = datetime.now(UTC)
    results = live.poll(config.RAW_DIR, read_setting("FIRMS_API_KEY"), now)
    for source in ("firms", "goes", "inpe"):
        of_source = [result for result in results if result["source"] == source]
        failed = [result["result"] for result in of_source if result["result"] != "ok"]
        new_rows = sum(result["new_rows"] for result in of_source)
        print(f"{source}: {len(of_source)} items, {new_rows} new rows, {len(failed)} failed.")
        for text in sorted(set(failed)):
            print(f"  {text}")
    new = live.ingest(config.RAW_DIR, open_store(config.STORE_PATH), now)
    print(f"store: {new} new detections.")
    # The replay of the year from its start is simple. It gets slow when the year has much data.
    run_fuse(now.year)
    if push:
        new_files = bucket.push(config.RAW_DIR, live.complete_logs(config.RAW_DIR, now))
        print(f"live: {new_files} complete logs copied to the bucket.")
