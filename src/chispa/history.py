"""The history of an event: its passes, when each became available, its alerts and its merges.

A brigade must know how late an alert was: the time from the first observation to the alert, and
the time from each pass to the moment when CHISPA had it. A pass is the item of evidence of the
fusion (`docs/method.md` 10.3): one scan of GOES, or the detections of one other platform in the
pass gap. Before the live logs, the time when a detection became available is an estimate.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

from chispa import config, live
from chispa.fusion import LEVELS
from chispa.issued import Replay
from chispa.store import to_text


def rises(found: dict, event_id: int) -> np.ndarray:
    """Return the positions of the detections that made the level of the event go up.

    Only the detections that joined this event count. An alert that it absorbed had its own
    levels before the merge: they are not the history of this event.
    """
    own = np.nonzero(found["issued"] == event_id)[0]
    highest = np.maximum.accumulate(found["level"][own])
    return own[np.nonzero(np.diff(highest, prepend=-1) > 0)[0]]


def pass_numbers(found: dict) -> np.ndarray:
    """Return the pass number of each detection, in the sequence of the first time of each pass.

    GOES times go back to the start of their scan, and only an equal scan is the same pass.
    For the other platforms, detections not farther apart than the pass gap are one pass.
    """
    goes = found["family"] == "abi"
    scan_s = config.GOES_SCAN.total_seconds()
    observed = found["observed"].astype(float)
    time = np.where(goes, observed - observed % scan_s, observed)
    order = np.lexsort((time, found["platform"]))
    names, times = found["platform"][order], time[order]
    gap = np.where(goes[order], 0.0, config.PASS_GAP.total_seconds())
    first = np.concatenate([[True], (names[1:] != names[:-1]) | (np.diff(times) > gap[1:])])
    start = times[first]
    rank = np.argsort(np.argsort(start, kind="stable"), kind="stable")
    numbers = np.empty(len(order), dtype=int)
    numbers[order] = rank[np.cumsum(first) - 1]
    return numbers


def passes(found: dict, event_id: int) -> tuple[list[dict], int]:
    """Return the passes to show and the number of all passes of the event.

    The passes to show are the newest passes (`config.py` gives how many) and each pass that
    made the level go up. They are in the sequence in which they became available: the sequence
    in which the fusion had them, and thus the sequence of the alerts.
    `alerts` has each level that the pass raised, with the time when CHISPA had the detection
    that raised it. The rows of one pass can come in two polls: FIRMS first, INPE later.
    `source` is the source of the first detection of the pass that CHISPA had.
    `estimated` is True for a pass before the live logs: then the time when it became available
    is the observation time plus an estimate (`config.AVAILABLE_DELAY`).
    """
    numbers = pass_numbers(found)
    count = int(numbers.max()) + 1
    # One pass can raise the level two times: LOW at its first detection, MEDIUM at a later one.
    raised: dict[int, list[dict]] = {}
    for i in rises(found, event_id):
        level = {"level": LEVELS[int(found["level"][i])], "at": _text(found["available"][i])}
        raised.setdefault(int(numbers[i]), []).append(level)
    shown = sorted(set(range(max(0, count - config.TOOL_MAX_PASSES), count)) | set(raised))
    live_s = config.LIVE_START.timestamp()
    rows = []
    for number in shown:
        members = np.nonzero(numbers == number)[0]
        power = found["frp_mw"][members]
        observed = float(found["observed"][members].min())
        rows.append(
            {
                "observed_at": _text(observed),
                "available_at": _text(found["available"][members].min()),
                "estimated": observed < live_s,
                "sensor_family": str(found["family"][members[0]]),
                "platform": str(found["platform"][members[0]]),
                "source": str(found["source"][members[0]]),
                "detections": len(members),
                "max_frp_mw": None if np.isnan(power).all() else float(np.nanmax(power)),
                "alerts": raised.get(number, []),
            }
        )
    return sorted(rows, key=lambda row: (row["available_at"], row["observed_at"])), count


def with_stops(rows: list[dict], raw_dir: Path) -> list[dict]:
    """Add to each pass the hours of its time to CHISPA in which the poller did not read its source.

    That time starts at the observation, or at the newest poll before that read the source with
    no failure (`live.answered_before`), and stops when CHISPA had the pass. It is the most that the
    poller added to the delay: the poll log does not say when the source published the pass.
    None: that time is not more than `config.LIVE_POLL_LATE`, or the pass has an estimated time.
    """
    answered: dict[tuple[str, str], datetime] = {}
    for row in rows:
        row["poller_stop_h"] = None
        if row["estimated"]:
            continue
        key = (row["available_at"], row["source"])
        at = datetime.fromisoformat(key[0])
        if key not in answered:
            answered[key] = live.answered_before(raw_dir, at, key[1])
        stop = at - max(answered[key], datetime.fromisoformat(row["observed_at"]))
        if stop > config.LIVE_POLL_LATE:
            row["poller_stop_h"] = round(stop / timedelta(hours=1), 2)
    return rows


def absorbed(replay: Replay, event_id: int) -> list[dict]:
    """Return each alert that merged into the event up to the moment of the replay, oldest first."""
    members = set(replay.ids(event_id))
    return [
        {"at": _text(time), "alert_id": stops, "into_id": continues}
        for time, stops, continues in replay.merges[: replay.done]
        if stops in members
    ]


def _text(seconds: float) -> str:
    return to_text(datetime.fromtimestamp(int(seconds), UTC))
