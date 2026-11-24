"""The watch of the live poller: a text to the owner each morning, and an alarm for a stop.

The server that records the live logs runs with no person. This module reads the poll log and
finds the texts that are due: a report each morning, an alarm when the poller is late, and one
text when it is good again. A log has each text, and the module reads its state from that log.
A server that is off sends no text: an absent morning text is then the sign.
"""

from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from chispa import config, polls
from chispa.sources import inpe

TEXTBELT = "https://textbelt.com/text"

# The sources of the report: the name in the poll log, and the name in the text.
SOURCES = {"firms": "FIRMS", "goes": "GOES", "inpe": "INPE"}

# A function that sends one text. It returns True for a text that went out, and a note.
Send = Callable[[str], tuple[bool, str]]


def run(raw_dir: Path, now: datetime, send: Send) -> list[tuple[str, bool]]:
    """Send each text that is due at `now`. Return (kind, True if it went out) for each text.

    The log has each text with its result. A text that failed is due again at the next run.
    """
    done = []
    for kind, text in due(raw_dir, now):
        sent, note = send(text)
        row = {"sent_at": now.isoformat(timespec="seconds"), "kind": kind}
        row |= {"result": "ok" if sent else "failed", "note": note, "text": text}
        polls.append_rows(raw_dir / "live" / "texts" / f"{now.date()}.csv", [row])
        done.append((kind, sent))
    return done


def due(raw_dir: Path, now: datetime) -> list[tuple[str, str]]:
    """Return (kind, text) for each text that is due at `now`.

    "late": the poller is late (`polls.status`), and the newest alarm text is not "late".
    "back": the poller is not late, and the newest alarm text is "late".
    "report": the local time of the owner is at or after the hour of the report, and no
    report went out on that local day.
    """
    status = polls.status(raw_dir, now)
    late = status["late_at"] is None or now > datetime.fromisoformat(status["late_at"])
    alarm = _newest(raw_dir, ("late", "back"))
    texts = []
    if late and (alarm is None or alarm["kind"] == "back"):
        texts.append(("late", _late_text(status, now)))
    if not late and alarm is not None and alarm["kind"] == "late":
        since = datetime.fromisoformat(alarm["sent_at"])
        good = f"CHISPA {now:%d %b %H:%M} UTC: the poller is good again."
        texts.append(("back", f"{good} It was late from {since:%d %b %H:%M} UTC."))
    zone = ZoneInfo(config.WATCH_TIME_ZONE)
    report = _newest(raw_dir, ("report",))
    day = report and datetime.fromisoformat(report["sent_at"]).astimezone(zone).date()
    local = now.astimezone(zone)
    if local.hour >= config.WATCH_REPORT_HOUR and day != local.date():
        texts.append(("report", report_text(raw_dir, now, late)))
    return texts


def report_text(raw_dir: Path, now: datetime, late: bool) -> str:
    """Return the morning text: what the poller did in the time of `config.WATCH_REPORT_SPAN`.

    It has the complete passes of the passes that the timer starts in that time, the passes
    with a failure, the GOES scans and the INPE files that no pass read, and the new rows of
    each source. The server has no store: the text has no event.
    """
    start = now - config.WATCH_REPORT_SPAN
    rows = _poll_rows(raw_dir, start, now)
    passes: dict[str, list[dict]] = {}
    for row in rows:
        passes.setdefault(row["polled_at"], []).append(row)
    complete = sum(polls.complete(polled_at, found) for polled_at, found in passes.items())
    failed = sum(any(row["result"] != "ok" for row in found) for found in passes.values())
    expected = int(config.WATCH_REPORT_SPAN / config.LIVE_POLL_EACH)
    end = now - config.WATCH_ITEM_MARGIN
    absent = {name: _not_read(rows, name, start, end) for name in ("goes", "inpe")}
    new = {
        name: sum(int(row["new_rows"]) for row in rows if row["source"] == name) for name in SOURCES
    }
    hours = config.WATCH_REPORT_SPAN / timedelta(hours=1)
    return (
        f"CHISPA {now:%d %b %H:%M} UTC: {'LATE' if late else 'OK'}. "
        f"{hours:g} h: {complete} of {expected} passes, {failed} with a failure. "
        f"Not read: GOES {absent['goes']}, INPE {absent['inpe']}. "
        f"New rows: {', '.join(f'{SOURCES[name]} {count}' for name, count in new.items())}."
    )


def send_text(text: str, phone: str, key: str) -> tuple[bool, str]:
    """Send one text with Textbelt. Return True if it went out, and a note for the log.

    The note has no key and no telephone number.
    """
    try:
        form = {"phone": phone, "message": text, "key": key}
        found = requests.post(TEXTBELT, data=form, timeout=60).json()
    except (requests.RequestException, ValueError) as error:
        return False, type(error).__name__
    if found.get("success"):
        return True, f"texts left: {found.get('quotaRemaining')}"
    return False, str(found.get("error")).replace(key, "[key]").replace(phone, "[number]")


def _late_text(status: dict, now: datetime) -> str:
    good = status["complete_pass_at"]
    since = f"{datetime.fromisoformat(good):%d %b %H:%M} UTC" if good else "none"
    sources = status["sources"] or {}
    failed = [SOURCES.get(name, name) for name, found in sources.items() if found["failed"]]
    cause = f"Failed in the newest pass: {', '.join(failed)}." if failed else "No pass ended."
    alarm = f"CHISPA ALARM {now:%d %b %H:%M} UTC: the poller is late."
    return f"{alarm} Newest good pass: {since}. {cause}"


def _newest(raw_dir: Path, kinds: tuple[str, ...]) -> dict | None:
    """Return the newest text of these kinds that went out, from the log of the texts."""
    for path in sorted((raw_dir / "live" / "texts").glob("*.csv"), reverse=True):
        for row in reversed(polls.read_rows(path)):
            if row["kind"] in kinds and row["result"] == "ok":
                return row
    return None


def _poll_rows(raw_dir: Path, start: datetime, now: datetime) -> list[dict]:
    """Return the rows of the poll log of each pass that started after `start`."""
    days = [start.date() + timedelta(days=n) for n in range((now.date() - start.date()).days + 1)]
    logs = [raw_dir / "live" / "polls" / f"{day}.csv" for day in days]
    rows = [row for path in logs for row in polls.read_rows(path)]
    return [row for row in rows if datetime.fromisoformat(row["polled_at"]) > start]


def _not_read(rows: list[dict], source: str, start: datetime, end: datetime) -> int:
    """Return the number of times of 10 minutes from `start` to `end` with no item of the
    source that a pass read. GOES has a scan, and INPE has a file, at each such time."""
    step = int(config.GOES_SCAN.total_seconds())
    read = set()
    for row in rows:
        if row["source"] == source and row["result"] == "ok":
            item = row["item"]
            time = inpe.live_time(item) if source == "inpe" else datetime.fromisoformat(item)
            read.add(int(time.timestamp()) // step)
    first, last = -(-int(start.timestamp()) // step), int(end.timestamp()) // step
    return sum(number not in read for number in range(first, last + 1))
