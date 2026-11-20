"""The command line: one entry point for each step of the work.

One command for each step lets a reader make each result again.
"""

import argparse
import os

from dotenv import load_dotenv

from chispa import bucket, config
from chispa.build import build_store
from chispa.sources import firms, goes, inpe, scars

NOT_BUILT = {
    "fuse": "Replay detections and write events and alerts.",
    "evaluate": "Compare alerts with burn scars and write the result tables.",
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
    fetch.add_argument("source", choices=["firms", "goes", "inpe"])
    fetch.add_argument("--year", type=int, required=True)
    fetch.add_argument("--push", action="store_true", help="Also copy new files to the bucket.")
    build = commands.add_parser("build", help="Make the store from the raw files.")
    build.add_argument("--offline", action="store_true", help="Do not get files from the bucket.")
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


def run_fetch(source: str, year: int, push: bool) -> None:
    """Download the raw files of one source from its origin. This does not change the store."""
    if source == "firms":
        files = firms.download_year(year, read_setting("FIRMS_API_KEY"), config.RAW_DIR)
    elif source == "inpe":
        files = inpe.download_year(year, config.RAW_DIR)
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
        print(f"{source}: {files} files, {detections} detections, {rejected} rows rejected.")
