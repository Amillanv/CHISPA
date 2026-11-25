"""The watch of the live poller: a text to the owner each morning, and an alarm for a stop.

The server that records the live logs runs with no person. This module reads the poll log and
finds the texts that are due: a report each morning, an alarm when the poller is late, and one
text when it is good again. A log has each text, and the module reads its state from that log.
A server that is off sends no text: an absent morning text is then the sign.
"""

import math
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
        texts.append(("late", _late_text(status)))
    if not late and alarm is not None and alarm["kind"] == "late":
        good = f"CHISPA is well again. The checks of the sources work as of {_when(now)}."
        since = _when(datetime.fromisoformat(alarm["sent_at"]))
        texts.append(("back", f"{good} The alarm went out at {since}."))
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
    each source. The server has no store: the text has no event. The text is for a person:
    it has full sentences, and a pass of the poller is a "check" in it.
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
    state = "CHISPA is running, but it had problems."
    if late:
        state = "CHISPA has a problem now: the checks of the sources are late."
    elif complete == expected and failed == 0 and not any(absent.values()):
        state = "CHISPA is well."
    hours = config.WATCH_REPORT_SPAN / timedelta(hours=1)
    span = f"{hours:g} hour" + ("" if hours == 1 else "s")
    checks = f"In the last {span} it checked the sources {complete} of {expected} times"
    checks += f", and {_count(failed, 'check')} had a failure." if failed else ", with no failure."
    missed = "It missed no scan and no file."
    if any(absent.values()):
        scans, files = _count(absent["goes"], "GOES scan"), _count(absent["inpe"], "INPE file")
        missed = f"It missed {scans} and {files}."
    found = ", ".join(f"{SOURCES[name]} {count:,}" for name, count in new.items())
    return f"{_greeting(now)}. {state} {checks} {missed} New detections: {found}."


def send_text(text: str, phone: str, key: str) -> tuple[bool, str]:
    """Send one text with Textbelt. Return True if it went out, and a note for the log.

    An answer that does not come counts as a failure, and the next run sends the text again.
    Thus a text can come two times, and an alarm cannot be lost.
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


def _late_text(status: dict) -> str:
    minutes = config.LIVE_POLL_LATE / timedelta(minutes=1)
    alarm = f"CHISPA alarm: no good check of the sources for {minutes:g} minutes."
    good = status["complete_pass_at"]
    last = "It has no good check."
    if good:
        last = f"The last good check was at {_when(datetime.fromisoformat(good))}."
    sources = status["sources"] or {}
    failed = [SOURCES.get(name, name) for name, found in sources.items() if found["failed"]]
    cause = f"{' and '.join(failed)} failed in the newest check." if failed else "No check ended."
    return f"{alarm} {last} {cause}"


def _when(time: datetime) -> str:
    """Return a time as the owner reads it: the day and the hour in the time zone of the owner."""
    return f"{time.astimezone(ZoneInfo(config.WATCH_TIME_ZONE)):%a %-I:%M %p %Z}"


def _greeting(now: datetime) -> str:
    hour = now.astimezone(ZoneInfo(config.WATCH_TIME_ZONE)).hour
    return "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"


def _count(number: int, name: str) -> str:
    """Return a number with its name: "1 GOES scan", "3 GOES scans"."""
    return f"{number:,} {name}" + ("" if number == 1 else "s")


def _newest(raw_dir: Path, kinds: tuple[str, ...]) -> dict | None:
    """Return the newest text of these kinds that went out, from the log of the texts."""
    for path in sorted((raw_dir / "live" / "texts").glob("*.csv"), reverse=True):
        for row in reversed(polls.read_rows(path)):
            if row["kind"] in kinds and row["result"] == "ok":
                return row
    return None


def _poll_rows(raw_dir: Path, start: datetime, now: datetime) -> list[dict]:
    """Return the rows of the poll log of each pass that started after `start`, to `now`."""
    days = [start.date() + timedelta(days=n) for n in range((now.date() - start.date()).days + 1)]
    logs = [raw_dir / "live" / "polls" / f"{day}.csv" for day in days]
    rows = [row for path in logs for row in polls.read_rows(path)]
    return [row for row in rows if start < datetime.fromisoformat(row["polled_at"]) <= now]


def _not_read(rows: list[dict], source: str, start: datetime, end: datetime) -> int:
    """Return the number of times of 10 minutes from `start` to `end` with no item of the
    source that a pass read. GOES has a scan, and INPE has a file, at each such time.
    An extra scan that started between two such times does not count for one of them."""
    step = config.GOES_SCAN.total_seconds()
    read = set()
    for row in rows:
        if row["source"] == source and row["result"] == "ok":
            item = row["item"]
            time = inpe.live_time(item) if source == "inpe" else datetime.fromisoformat(item)
            if time.timestamp() % step == 0:
                read.add(int(time.timestamp() // step))
    first, last = math.ceil(start.timestamp() / step), math.floor(end.timestamp() / step)
    return sum(number not in read for number in range(first, last + 1))
