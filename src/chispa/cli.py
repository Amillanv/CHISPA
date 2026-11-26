"""The command line: one entry point for each step of the work.

One command for each step lets a reader make each result again.
"""

import argparse
import os
from datetime import UTC, datetime, timedelta
from functools import partial

from dotenv import load_dotenv

from chispa import bucket, checks, config, live, polls, watch
from chispa.build import add_live, build_store
from chispa.evaluation.report import write_summary, write_tables
from chispa.evaluation.run import evaluate
from chispa.fusion import LEVELS, fuse
from chispa.grid import layer_grid, pantanal_grid
from chispa.sources import (
    border,
    burnday,
    burned,
    firms,
    goes,
    inpe,
    landcover,
    monitor,
    passes,
    protected,
    river,
    scars,
    settlements,
    weather,
)
from chispa.store import clear_stale, open_store, read_detections, replace_fusion, stale_years
from chispa.web import server

YEAR_SOURCES = ("firms", "goes", "goes_mask", "inpe", "passes", "scars", "burnday", "landcover")
YEAR_SOURCES += ("weather", "burned", "river", "monitor")
FIXED_SOURCES = ("border", "protected", "settlements")
NOT_BUILT = {
    "mcp": "Start the MCP server.",
    "grade": "Run the gold questions and grade the answers.",
}


def main(arguments: list[str] | None = None) -> None:
    """Read the command and run it."""
    parser = argparse.ArgumentParser(prog="chispa", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="Do a check of the keys and the logins.")
    fetch = commands.add_parser("fetch", help="Get the raw files of one source for one year.")
    fetch.add_argument("source", choices=[*YEAR_SOURCES, *FIXED_SOURCES])
    fetch.add_argument("--year", type=int, help="Necessary for a source that has years.")
    fetch.add_argument("--push", action="store_true", help="Also copy new files to the bucket.")
    build = commands.add_parser("build", help="Make the store from the raw files.")
    build.add_argument("--offline", action="store_true", help="Do not get files from the bucket.")
    fusion = commands.add_parser("fuse", help="Replay one year of detections into events.")
    fusion.add_argument("--year", type=int, required=True)
    evaluation = commands.add_parser("evaluate", help="Compare one fused year with the fires.")
    evaluation.add_argument("--year", type=int, required=True)
    evaluation.add_argument("--test-run", action="store_true", help="Permit the test year.")
    names = {"burn": "burn check", "images": "image check", "visibility": "visibility table"}
    names["candidates"] = "table of the candidates for the burned ground"
    names["curve"] = "burn curve of the boxes of the burn check"
    names["pixels"] = "table of the burned pixels of the rule against the map"
    names["advance"] = "table of the advance of VIIRS against the new burned ground"
    names |= {"growth": "growth table", "severity": "severity tables"}
    names["confidence"] = "confidence tables"
    for name, text in names.items():
        check = commands.add_parser(name, help=f"Make the {text} of one fused year.")
        check.add_argument("--year", type=int, required=True)
        check.add_argument("--test-run", action="store_true", help="Permit the test year.")
        if name == "curve":
            each = "Measure each event of the year in the biome, not the boxes of the burn check."
            check.add_argument("--events", action="store_true", help=each)
        if name == "images":
            look = "1: the first look. 2: the same events again and boxes with no fire."
            check.add_argument("--look", type=int, choices=(1, 2), default=1, help=look)
    risk = commands.add_parser("risk", help="Make the growth risk tables of each year with fires.")
    risk.add_argument("--test-run", action="store_true", help="Also score the test year one time.")
    poll = commands.add_parser("poll", help="Do one pass of the live poller: record the new rows.")
    since = "Read back the GOES scans and the INPE files to this UTC time, to fill a hole: "
    since += "2026-11-20T00:00:00+00:00. It does not change the FIRMS request."
    poll.add_argument("--since", type=datetime.fromisoformat, help=since)
    commands.add_parser("update", help="Put the live logs into the store and the events.")
    commands.add_parser("watch", help="Send each text that is due: the report or an alarm.")
    dashboard = commands.add_parser("serve", help="Start the dashboard on this computer.")
    dashboard.add_argument("--port", type=int, default=8000)
    for name, text in NOT_BUILT.items():
        commands.add_parser(name, help=f"{text} Not built.")
    chosen = parser.parse_args(arguments)
    load_dotenv()
    permit_year(chosen)
    if chosen.command == "check":
        check()
    elif chosen.command == "fetch":
        run_fetch(chosen.source, chosen.year, chosen.push)
    elif chosen.command == "build":
        run_build(chosen.offline)
    elif chosen.command == "fuse":
        run_fuse(chosen.year)
    elif chosen.command == "evaluate":
        run_evaluate(chosen.year)
    elif chosen.command == "advance":
        checks.run_advance(chosen.year, lambda: read_setting("EE_PROJECT"))
    elif chosen.command == "pixels":
        checks.run_pixels(chosen.year, lambda: read_setting("EE_PROJECT"))
    elif chosen.command == "curve":
        run = checks.run_event_curves if chosen.events else checks.run_curve
        run(chosen.year, lambda: read_setting("EE_PROJECT"))
    elif chosen.command == "candidates":
        checks.run_candidates(chosen.year, lambda: read_setting("EE_PROJECT"))
    elif chosen.command == "burn":
        checks.run_burn(chosen.year, lambda: read_setting("EE_PROJECT"))
    elif chosen.command in ("visibility", "growth", "severity", "confidence"):
        checks.run_table(chosen.command, chosen.year)
    elif chosen.command == "risk":
        checks.run_risk(chosen.test_run)
    elif chosen.command == "images":
        checks.run_images(chosen.year, lambda: read_setting("EE_PROJECT"), chosen.look)
    elif chosen.command == "poll":
        run_poll(chosen.since)
    elif chosen.command == "update":
        run_update()
    elif chosen.command == "watch":
        key, phone = read_setting("TEXTBELT_KEY"), read_setting("ALERT_PHONE_NUMBER")
        send = partial(watch.send_text, phone=phone, key=key)
        done = watch.run(config.RAW_DIR, datetime.now(UTC), send)
        for kind, sent in done:
            print(f"watch: the text '{kind}' {'went out' if sent else 'failed'}.")
        if not all(sent for _, sent in done):
            raise SystemExit(1)  # The service then shows the run as failed.
    elif chosen.command == "serve":
        server.serve(chosen.port)
    else:
        parser.exit(1, f"The command '{chosen.command}' is not built.\n")


def permit_year(chosen: argparse.Namespace) -> None:
    """Stop a command that makes results for a test year, unless the person asked for that run.

    A test year scores a part one time. A run by accident shows its results too early.
    """
    is_result = chosen.command in (
        "evaluate",
        "burn",
        "candidates",
        "curve",
        "pixels",
        "advance",
        "images",
        "visibility",
        "growth",
        "severity",
        "confidence",
    )
    test_years = (config.TEST_YEAR, config.PART_TEST_YEAR)
    if is_result and chosen.year in test_years and not chosen.test_run:
        role = config.YEAR_ROLES[chosen.year]
        raise SystemExit(
            f"{chosen.year} is the {role}. Freeze the rules of the part first, then add --test-run."
        )


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
    elif source in ("passes", "river"):
        module = {"passes": passes, "river": river}[source]
        files = module.download_year(year, config.RAW_DIR)
    elif source == "goes_mask":
        yesterday = datetime.now(UTC).date() - timedelta(days=1)
        files = goes.download_masks(year, config.RAW_DIR, yesterday)
    elif source in ("scars", "monitor"):
        module, project = {"scars": scars, "monitor": monitor}[source], read_setting("EE_PROJECT")
        files = module.download_year(year, project, config.RAW_DIR, pantanal_grid())
    elif source in ("burnday", "weather", "burned"):
        module = {"burnday": burnday, "weather": weather, "burned": burned}[source]
        files = module.download_year(year, read_setting("EE_PROJECT"), config.RAW_DIR)
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
    fusion = fuse(read_detections(store, start, end), first_id)
    replace_fusion(store, (first_id, first_id + 10_000_000), fusion)
    events, _, memberships, merges = fusion
    levels = {level: sum(event.level == level for event in events) for level in LEVELS}
    issued = len(events) + len(merges)
    print(
        f"{year}: {len(memberships)} detections, {issued} alerts, {len(events)} events, {levels}."
    )


def run_evaluate(year: int) -> None:
    """Write the result tables of one year."""
    write_tables(evaluate(year, config.STORE_PATH, config.RAW_DIR), year, config.RESULTS_DIR)
    write_summary(config.RESULTS_DIR)
    print(f"{year}: the tables are in {config.RESULTS_DIR / str(year)}. See results/SUMMARY.md.")


def run_poll(since: datetime | None) -> None:
    """Do one pass of the live poller: record each new row with the time of the pass.

    A pass does not change the store. Thus a small server can record, and `update` can run
    on a different computer that has a copy of the logs.
    """
    if since is not None and since.utcoffset() is None:
        raise SystemExit("Give --since with a time zone: 2026-11-20T00:00:00+00:00.")
    if since is not None and since < config.LIVE_START:
        start = config.LIVE_START.date()
        raise SystemExit(f"The live logs start on {start}. For the days before it, use `fetch`.")
    now = datetime.now(UTC)
    results = live.poll(config.RAW_DIR, read_setting("FIRMS_API_KEY"), now, since)
    back = max(since or now - config.LIVE_LOOKBACK, config.LIVE_START).astimezone(UTC)
    print(f"asked: FIRMS for {config.LIVE_FIRMS_DAYS} days. INPE from {back:%Y-%m-%d %H:%M} UTC.")
    print(
        "asked: GOES from the same time, or from the newest scan that a pass read if it is older."
    )
    for source in ("firms", "goes", "inpe"):
        of_source = [result for result in results if result["source"] == source]
        failed = [result["result"] for result in of_source if result["result"] != "ok"]
        new_rows = sum(result["new_rows"] for result in of_source)
        print(f"{source}: {len(of_source)} items, {new_rows} new rows, {len(failed)} failed.")
        for text in sorted(set(failed)):
            print(f"  {text}")


def run_update() -> None:
    """Add the detections of the live logs to the store, then make the events again for each
    year with a mark: its events are older than its detections."""
    now = datetime.now(UTC)
    store = open_store(config.STORE_PATH)
    new, rejected = add_live(config.RAW_DIR, store)
    print(f"store: {new} new detections, {rejected} rows rejected.")
    # In January a log of December can get a row: then the year before has a mark also.
    # The replay of a year from its start is simple. It gets slow when the year has much data.
    # The mark of a year goes only after its fusion: an update that stops makes it the next time.
    for year in stale_years(store):
        run_fuse(year)
        clear_stale(store, year)
    status = polls.status(config.RAW_DIR, now)
    if status["late_at"] is None or now > datetime.fromisoformat(status["late_at"]):
        newest = status["complete_pass_at"] or "no pass"
        print(f"live: LATE. The newest pass with no failure: {newest}. Do a check of the poller.")
