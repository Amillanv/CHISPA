"""The poll log: what each pass of the live poller read, and how old the live data is.

The poller writes one row for each product, scan and file of a pass. This module reads those
rows: for the lag of the live data, and for the time of the read before the pass of a row.
"""

import csv
from datetime import UTC, datetime
from pathlib import Path

from chispa import config

# The source of a detection, as the poll log names it. The GOES rows of the poller come from NOAA.
POLL_SOURCE = {"firms": "firms", "inpe": "inpe", "noaa": "goes"}


def read_rows(path: Path) -> list[dict]:
    """Return the rows of one log. A log that is absent has no rows."""
    if not path.exists():
        return []
    with path.open(newline="") as file:
        return list(csv.DictReader(file))


def status(raw_dir: Path, as_of: datetime) -> dict:
    """Return how old the live data was at the as-of time, from the poll log.

    `archive` is True before the first day of the live logs: then the store has archive data.
    `newest_pass_at` is the newest pass, with a result for each source. `complete_pass_at` is the
    newest pass in which no source failed: the store has the data of each source to that pass.
    A pass in which a source failed does not make the data newer. `late_at` is the time from which
    the data is late. The answer gives no failure text: a text can hold a key or an address.
    """
    found = {"archive": as_of < config.LIVE_START, "newest_pass_at": None, "sources": None}
    found |= {"complete_pass_at": None, "late_at": None}
    for polled_at, rows in _passes(raw_dir, as_of):
        if found["newest_pass_at"] is None:
            found |= {"newest_pass_at": polled_at, "sources": _results(rows)}
        if all(row["result"] == "ok" for row in rows):
            late = datetime.fromisoformat(polled_at) + config.LIVE_POLL_LATE
            return found | {"complete_pass_at": polled_at, "late_at": late.isoformat()}
    return found


def answered_before(raw_dir: Path, at: datetime, source: str) -> datetime:
    """Return the time of the newest poll that read a source with no failure, before the pass
    that first saw a row at `at`.

    `source` is the source of a detection. The pass of the row is the newest pass that started
    at or before `at`: a row has the time of its read, at or after the start of its pass.
    A poll with no row for the source read nothing new and had no failure (`_results`).
    Before the first such poll: the first day of the live logs.
    """
    name = POLL_SOURCE[source]
    passes = _passes(raw_dir, at)
    next(passes, None)  # The pass that saw the row.
    for polled_at, rows in passes:
        if not any(row["source"] == name and row["result"] != "ok" for row in rows):
            return datetime.fromisoformat(polled_at)
    return config.LIVE_START


def _passes(raw_dir: Path, as_of: datetime):
    """Give (time, rows) for each pass at or before the as-of time, the newest first."""
    day = as_of.astimezone(UTC).date().isoformat()
    for path in sorted((raw_dir / "live" / "polls").glob("*.csv"), reverse=True):
        if path.stem > day:
            continue
        passes: dict[str, list[dict]] = {}
        for row in read_rows(path):
            if datetime.fromisoformat(row["polled_at"]) <= as_of:
                passes.setdefault(row["polled_at"], []).append(row)
        yield from sorted(
            passes.items(), key=lambda item: datetime.fromisoformat(item[0]), reverse=True
        )


def _results(rows: list[dict]) -> dict[str, dict]:
    """Return, for each source of one pass, its items, its failed items and its new rows.

    A source with no row read no new scan or file and recorded no failure in that pass.
    """
    sources: dict[str, dict] = {}
    for row in rows:
        found = sources.setdefault(row["source"], {"items": 0, "failed": 0, "new_rows": 0})
        found["items"] += 1
        found["failed"] += row["result"] != "ok"
        found["new_rows"] += int(row["new_rows"])
    return sources
