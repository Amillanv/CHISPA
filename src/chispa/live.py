"""The live poller: get new detections from the live sources and record when we first saw them.

Recorded data does not say when a detection became available. One pass of the poller gets
the newest data of each live source and appends each new row to a log, with the time of its read.
The logs are raw files: they only grow, and `build` can read them again.
"""

import csv
import gzip
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import requests

from chispa import config
from chispa.polls import PASS_END, read_rows
from chispa.sources import firms, goes, inpe

# The fields that identify one FIRMS row. A row that we saw before is not a new detection.
FIRMS_KEY = ("satellite", "acq_date", "acq_time", "latitude", "longitude")

# The clock of one pass: it gives the time of a read.
Clock = Callable[[], datetime]


def poll(raw_dir: Path, key: str, now: datetime, since: datetime | None = None) -> list[dict]:
    """Do one pass that starts at `now`. Return one result for each product, scan and file,
    and one last result for the pass.

    A pass reads each GOES scan and each INPE file from `since` that no pass read. With no
    `since` it reads back `config.LIVE_LOOKBACK`. It does not read back to before
    `config.LIVE_START`. `since` does not change the FIRMS request.
    INPE removes a file after some days: a stop of that length loses INPE files.
    A source that fails does not stop the pass. The next pass gets its data.
    """
    live = raw_dir / "live"
    # The live logs start at `config.LIVE_START`: the archive has the data from before it.
    since = max(since or now - config.LIVE_LOOKBACK, config.LIVE_START).astimezone(UTC)
    started = time.monotonic()

    def clock() -> datetime:
        # A row has the time of its read: a long pass reads its last file minutes after its start.
        return now + timedelta(seconds=time.monotonic() - started)

    # FIRMS is the first read of a pass. Thus the start of a pass is the time of its FIRMS read,
    # to some seconds: `build.after_stop` finds a stop from the starts of the passes.
    results = [_poll_firms(live, product, key, now, clock) for product in firms.LIVE_PRODUCTS]
    results += _poll_goes(live, since, now, clock) + _poll_inpe(live, since, now, clock)
    # The last row of a pass says that the pass read each source. A pass that stops has none.
    new_rows = sum(result["new_rows"] for result in results)
    return [*results, _log(live, _result(now, PASS_END, "end", "ok", new_rows))]


def _result(now: datetime, source: str, item: str, result: str, new_rows: int) -> dict:
    return {
        "polled_at": now.isoformat(timespec="seconds"),
        "source": source,
        "item": item,
        "result": result,
        "new_rows": new_rows,
    }


def _log(live: Path, result: dict) -> dict:
    """Write one result to the poll log at once, and return it. Thus a pass that stops in the
    middle reads again only the item that it did not complete."""
    _append(live / "polls" / f"{result['polled_at'][:10]}.csv", [result])
    return result


def _poll_firms(live: Path, product: str, key: str, now: datetime, clock: Clock) -> dict:
    """Append the rows of one FIRMS product that are not in its logs. One log for each day."""
    try:
        rows = firms.download_live(product, key)
    except RuntimeError as error:  # The message of this error does not contain the key.
        return _log(live, _result(now, "firms", product, f"failed: {error}", 0))
    seen_at, new_rows = clock().isoformat(timespec="seconds"), 0
    for day in sorted({row["acq_date"] for row in rows}):
        path = live / "firms" / product / f"{day}.csv"
        seen = {tuple(row[name] for name in FIRMS_KEY) for row in read_rows(path)}
        fresh = {}
        for row in rows:
            identity = tuple(row[name] for name in FIRMS_KEY)
            if row["acq_date"] == day and identity not in seen:
                fresh[identity] = {**row, "first_seen_at": seen_at}
        _append(path, list(fresh.values()))
        new_rows += len(fresh)
    return _log(live, _result(now, "firms", product, "ok", new_rows))


def _done(live: Path, source: str, since: datetime, now: datetime) -> set[str]:
    """Return the items of one source that a pass read, from the day of `since`."""
    days = [since.date() + timedelta(days=n) for n in range((now.date() - since.date()).days + 1)]
    return {
        row["item"]
        for day in days
        for row in read_rows(live / "polls" / f"{day}.csv")
        if row["source"] == source and row["result"] == "ok"
    }


def _newest_read(live: Path, source: str) -> str | None:
    """Return the newest item of one source that a pass read. None: no pass read an item."""
    for path in sorted((live / "polls").glob("*.csv"), reverse=True):
        rows = [row for row in read_rows(path) if row["source"] == source]
        items = [row["item"] for row in rows if row["result"] == "ok"]
        if items:
            return max(items)
    return None


def _times(seen_at: datetime, published_at: datetime) -> dict:
    return {
        "first_seen_at": seen_at.isoformat(timespec="seconds"),
        "published_at": published_at.isoformat(timespec="seconds"),
    }


def _poll_goes(live: Path, since: datetime, now: datetime, clock: Clock) -> list[dict]:
    """Read each GOES scan from `since` that no pass read before. Append its fire pixels to a log,
    and its mask counts to a second log. Each row has the time of the read of its scan."""
    # The NOAA bucket keeps each file. Thus a pass reads back to the newest scan that a pass
    # read, if that scan is older than `since`: a stop of each length gets its scans.
    newest = _newest_read(live, "goes")
    since = min(since, datetime.fromisoformat(newest)) if newest else since
    done = _done(live, "goes", since, now)
    results = []
    try:
        scans = goes.list_live(since, now)
        new_scans = [scan for scan in scans if scan[1].isoformat() not in done]
        if new_scans and not (live / "goes_mask" / "grid.npz").exists():
            lat, lon = goes.mask_grid(new_scans[0])
            (live / "goes_mask").mkdir(parents=True, exist_ok=True)
            np.savez_compressed(live / "goes_mask" / "grid.npz", lat=lat, lon=lon)
        for observed_at, published_at, pixels, mask_counts, mask in goes.read_live(new_scans):
            times = _times(clock(), published_at)
            rows = [
                dict(zip(goes.COLUMNS, [observed_at.isoformat(), *pixel], strict=True)) | times
                for pixel in pixels
            ]
            _append(live / "goes" / f"{observed_at.date()}.csv", rows)
            # A scan with no fire pixel gives no row above. This row says what the scan could see.
            seen = {"observed_at": observed_at.isoformat()} | mask_counts | times
            _append(live / "goes_mask" / f"{observed_at.date()}.csv", [seen])
            _add_mask(live / "goes_mask" / str(observed_at.year), observed_at, times, mask)
            result = _result(now, "goes", observed_at.isoformat(), "ok", len(rows))
            results.append(_log(live, result))
    except requests.RequestException as error:
        result = _result(now, "goes", "request", f"failed: {type(error).__name__}", 0)
        results.append(_log(live, result))
    return results


def _poll_inpe(live: Path, since: datetime, now: datetime, clock: Clock) -> list[dict]:
    """Read each INPE file of 10 minutes from `since` that no pass read before.
    Keep the full file, and append its rows in the Pantanal box to a log."""
    done = _done(live, "inpe", since, now)
    results = []
    try:
        for name in inpe.list_live(since, now):
            if name in done:
                continue
            published_at, content = inpe.read_live(name)
            rows = keep_inpe(live, name, content, _times(clock(), published_at))
            results.append(_log(live, _result(now, "inpe", name, "ok", rows)))
    except requests.RequestException as error:
        result = _result(now, "inpe", "request", f"failed: {type(error).__name__}", 0)
        results.append(_log(live, result))
    return results


def keep_inpe(live: Path, name: str, content: bytes, times: dict) -> int:
    """Save one INPE file as it came, and append its rows in the Pantanal box to the log.

    INPE removes a file after some days, and the log has only the rows in the box. The full file
    keeps the rows of the other regions. A list for each day has the times of each file.
    Return the number of rows in the box.
    """
    day = str(inpe.live_time(name).date())
    folder = live / "inpe_files" / day
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.gz").write_bytes(gzip.compress(content, mtime=0))
    _append(live / "inpe_files" / f"{day}.csv", [{"file": name} | times])
    rows = [row | times for row in inpe.box_rows(content)]
    _append(live / "inpe" / f"{day}.csv", rows)
    return len(rows)


def _add_mask(folder: Path, observed_at: datetime, times: dict, mask: np.ndarray) -> None:
    """Add the mask of one scan to the mask file of its day, with the time when we first had it
    and the publication time of its file.

    The file has the form of the recorded masks. Thus the event record reads the two in one way:
    for a place, it can say if GOES examined it, or if cloud hid it.
    """
    path = folder / f"{observed_at.date()}.npz"
    scans = seen = published = np.array([], dtype="U25")
    masks = np.empty((0, *mask.shape), dtype=np.uint8)
    if path.exists():
        day = np.load(path)
        scans, masks = day["times"], day["mask"]
        # A file of an earlier version has no time of the first view, or no publication time.
        # For its scans we use the scan start plus the delay of a raw file, as for a recorded mask.
        estimate = np.array([_had_at(scan) for scan in scans])
        seen = day["seen"] if "seen" in day else estimate
        published = day["published"] if "published" in day else estimate
        if observed_at.isoformat() in scans:
            return  # A pass that stopped after this write reads the scan again.
    folder.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(".part.npz")  # A pass that stops in the middle does not break the file.
    np.savez_compressed(
        part,
        times=np.append(scans, observed_at.isoformat()),
        seen=np.append(seen, times["first_seen_at"]),
        published=np.append(published, times["published_at"]),
        mask=np.concatenate([masks, mask[None]]),
    )
    part.replace(path)


def _had_at(scan_start: str) -> str:
    return (datetime.fromisoformat(str(scan_start)) + config.GOES_RAW_DELAY).isoformat()


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
