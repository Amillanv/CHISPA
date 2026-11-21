"""The command line: one entry point for each step of the work.

One command for each step lets a reader make each result again.
"""

import argparse
import os
from datetime import UTC, datetime

from dotenv import load_dotenv

from chispa import bucket, config
from chispa.build import build_store
from chispa.evaluate import evaluate
from chispa.fusion import LEVELS, fuse
from chispa.grid import pantanal_grid
from chispa.report import write_summary, write_tables
from chispa.sources import border, burnday, firms, goes, inpe, scars
from chispa.store import open_store, read_detections, replace_fusion

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
    fetch.add_argument("source", choices=["firms", "goes", "inpe", "scars", "burnday", "border"])
    fetch.add_argument("--year", type=int, help="Necessary for each source apart from border.")
    fetch.add_argument("--push", action="store_true", help="Also copy new files to the bucket.")
    build = commands.add_parser("build", help="Make the store from the raw files.")
    build.add_argument("--offline", action="store_true", help="Do not get files from the bucket.")
    fusion = commands.add_parser("fuse", help="Replay one year of detections into events.")
    fusion.add_argument("--year", type=int, required=True)
    evaluation = commands.add_parser("evaluate", help="Compare one fused year with the scars.")
    evaluation.add_argument("--year", type=int, required=True)
    evaluation.add_argument("--test-run", action="store_true", help="Permit the test year.")
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
    if source != "border" and year is None:
        raise SystemExit("Give the year: --year 2024.")
    if source == "firms":
        files = firms.download_year(year, read_setting("FIRMS_API_KEY"), config.RAW_DIR)
    elif source == "inpe":
        files = inpe.download_year(year, config.RAW_DIR)
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
        print(f"{source}: {bucket.push(config.RAW_DIR, source)} new files copied to the bucket.")


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
