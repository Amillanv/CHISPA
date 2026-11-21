"""The live poller: get new detections from the live sources and record when we first saw them.

Recorded data does not say when a detection became available. One pass of the poller gets
the newest data of each live source and appends each new row to a log, with the time of the pass.
The logs are raw files: they only grow, and `build` can read them again.
"""

import csv
from datetime import datetime, timedelta
from pathlib import Path

import requests

from chispa import config
from chispa.sources import firms, goes, inpe

# The fields that identify one FIRMS row. A row that we saw before is not a new detection.
FIRMS_KEY = ("satellite", "acq_date", "acq_time", "latitude", "longitude")


def poll(raw_dir: Path, key: str, now: datetime) -> list[dict]:
    """Do one pass at the time `now`. Return one result for each product, scan and file.

    A source that fails does not stop the pass. The next pass gets its data.
    """
    live = raw_dir / "live"
    results = [_poll_firms(live, product, key, now) for product in firms.LIVE_PRODUCTS]
    results += _poll_goes(live, now) + _poll_inpe(live, now)
    _append(live / "polls" / f"{now.date()}.csv", results)
    return results


def _result(now: datetime, source: str, item: str, result: str, new_rows: int) -> dict:
    return {
        "polled_at": now.isoformat(timespec="seconds"),
        "source": source,
        "item": item,
        "result": result,
        "new_rows": new_rows,
    }


def _poll_firms(live: Path, product: str, key: str, now: datetime) -> dict:
    """Append the rows of one FIRMS product that are not in its logs. One log for each day."""
    try:
        rows = firms.download_live(product, key)
    except RuntimeError as error:  # The message of this error does not contain the key.
        return _result(now, "firms", product, f"failed: {error}", 0)
    new_rows = 0
    for day in sorted({row["acq_date"] for row in rows}):
        path = live / "firms" / product / f"{day}.csv"
        seen = {tuple(row[name] for name in FIRMS_KEY) for row in _read(path)}
        fresh = {}
        for row in rows:
            identity = tuple(row[name] for name in FIRMS_KEY)
            if row["acq_date"] == day and identity not in seen:
                fresh[identity] = {**row, "first_seen_at": now.isoformat(timespec="seconds")}
        _append(path, list(fresh.values()))
        new_rows += len(fresh)
    return _result(now, "firms", product, "ok", new_rows)


def _done(live: Path, source: str, now: datetime) -> set[str]:
    """Return the items of one source that a pass of today or of the day before read."""
    days = (now.date() - timedelta(days=1), now.date())
    return {
        row["item"]
        for day in days
        for row in _read(live / "polls" / f"{day}.csv")
        if row["source"] == source and row["result"] == "ok"
    }


def _times(now: datetime, published_at: datetime) -> dict:
    return {
        "first_seen_at": now.isoformat(timespec="seconds"),
        "published_at": published_at.isoformat(timespec="seconds"),
    }


def _poll_goes(live: Path, now: datetime) -> list[dict]:
    """Read each GOES scan that no pass read before. Append its fire pixels to a log."""
    done = _done(live, "goes", now)
    results = []
    try:
        new_scans = [scan for scan in goes.list_live(now) if scan[1].isoformat() not in done]
        for observed_at, published_at, pixels in goes.read_live(new_scans):
            rows = [
                dict(zip(goes.COLUMNS, [observed_at.isoformat(), *pixel], strict=True))
                | _times(now, published_at)
                for pixel in pixels
            ]
            _append(live / "goes" / f"{observed_at.date()}.csv", rows)
            results.append(_result(now, "goes", observed_at.isoformat(), "ok", len(rows)))
    except requests.RequestException as error:
        results.append(_result(now, "goes", "request", f"failed: {type(error).__name__}", 0))
    return results


def _poll_inpe(live: Path, now: datetime) -> list[dict]:
    """Read each INPE file of 10 minutes that no pass read before. Append its rows to a log."""
    done = _done(live, "inpe", now)
    results = []
    try:
        for name in inpe.list_live(now):
            if name in done:
                continue
            published_at, rows = inpe.read_live(name)
            rows = [row | _times(now, published_at) for row in rows]
            _append(live / "inpe" / f"{inpe.live_time(name).date()}.csv", rows)
            results.append(_result(now, "inpe", name, "ok", len(rows)))
    except requests.RequestException as error:
        results.append(_result(now, "inpe", "request", f"failed: {type(error).__name__}", 0))
    return results


def complete_logs(raw_dir: Path, now: datetime) -> list[Path]:
    """Return the logs that get no more rows. Only these logs can go to the bucket,
    because a file in the bucket never changes."""
    last = (now - config.LIVE_COMPLETE_AFTER).date().isoformat()
    return sorted(path for path in (raw_dir / "live").rglob("*.csv") if path.stem <= last)


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="") as file:
        return list(csv.DictReader(file))


def _append(path: Path, rows: list[dict]) -> None:
    """Add rows to the end of a log. A new log gets a header line."""
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    with path.open("a", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        if is_new:
            writer.writeheader()
        writer.writerows(rows)
