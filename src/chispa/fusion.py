"""The fusion: group detections into events and give each event a confidence level.

The method uses a grid of cells. A detection occupies the cells that its footprint covers.
Two detections that occupy the same cell, not far apart in time, are the same event.
The fusion reads detections in the sequence in which they became available.
Thus each alert uses only what a brigade could know at that time.
"""

import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from chispa import config
from chispa.models import Alert, Detection, Event

LEVELS = ("LOW", "MEDIUM", "HIGH")
WINDOW_S = config.FUSION_WINDOW.total_seconds()
PASS_GAP_S = config.PASS_GAP.total_seconds()
SCAN_S = config.GOES_SCAN.total_seconds()


@dataclass
class _State:
    """The working state of one event during the replay."""

    families: set = field(default_factory=set)
    passes: dict = field(default_factory=dict)  # (family, platform) -> time of each pass
    has_high: bool = False
    count: int = 0
    first_observed: float = math.inf
    last_observed: float = -math.inf
    first_available: float = math.inf
    sum_lat: float = 0.0
    sum_lon: float = 0.0
    box: list = field(default_factory=lambda: [90.0, 180.0, -90.0, -180.0])  # s, w, n, e
    max_frp_mw: float | None = None


def fuse(detections: Iterable[tuple[int, Detection]], first_id: int) -> tuple[list, ...]:
    """Replay detections and return the events, the alert changes, the memberships and the merges.

    A membership is (detection id, event id, level of the event after this detection, issued id).
    The event id is the event at the end of the replay. The issued id is the event that the
    detection joined at its time: the alert as a brigade got it. A merge is (time, the event
    that stops, the event that continues). With the issued ids and the merges up to a time,
    we get the events as they were at that time.
    The detections must be in `available_at` sequence.
    """
    cells: dict[tuple[int, int], list] = {}  # cell -> [event number, last observation time]
    parent: list[int] = []  # When two events merge, the newer points to the older.
    states: dict[int, _State] = {}
    changes, members, merges = [], [], []
    for detection_id, detection in detections:
        observed = detection.observed_at.timestamp()
        covered = _cells(detection)
        root, before, absorbed = _join(covered, observed, cells, parent, states)
        merges += [
            (detection.available_at, first_id + other, first_id + root) for other in absorbed
        ]
        state = states[root]
        _add(state, detection, observed)
        for cell in covered:
            cells[cell] = [root, max(observed, cells[cell][1]) if cell in cells else observed]
        level = _level(state)
        members.append((detection_id, root, level))
        if level != before:
            changes.append((root, detection.available_at, level, _families(state), _passes(state)))
    final = [_find(parent, number) for number in range(len(parent))]
    events = [_event(first_id + number, state) for number, state in sorted(states.items())]
    alerts = [
        Alert(first_id + number, at, level, fam, passes)
        for number, at, level, fam, passes in _rises(changes, final)
    ]
    memberships = [(d, first_id + final[n], level, first_id + n) for d, n, level in members]
    return events, alerts, memberships, merges


def _rises(changes: list[tuple], final: list[int]) -> list[tuple]:
    """Return the changes that make the level of a final event go up, with the final number.

    A merged event holds the changes of each event that it absorbed. Without this step,
    its alert has the same level two times. The changes are in `available_at` sequence.
    The families and the passes of a row are those of the part that gave the new level.
    """
    highest: dict[int, int] = {}
    rises = []
    for number, at, level, families, passes in changes:
        event = final[number]
        if LEVELS.index(level) > highest.get(event, -1):
            highest[event] = LEVELS.index(level)
            rises.append((event, at, level, families, passes))
    return rises


def _cells(detection: Detection) -> list[tuple[int, int]]:
    """Return the cells of the square that holds the footprint plus the margin."""
    reach_m = detection.footprint_m + config.FUSION_MARGIN_M
    d_lat = reach_m / 110_574
    d_lon = reach_m / (111_320 * math.cos(math.radians(detection.lat)))
    cell = config.FUSION_CELL_DEG
    rows = range(
        math.floor((detection.lat - d_lat) / cell), math.floor((detection.lat + d_lat) / cell) + 1
    )
    cols = range(
        math.floor((detection.lon - d_lon) / cell), math.floor((detection.lon + d_lon) / cell) + 1
    )
    return [(row, col) for row in rows for col in cols]


def _join(covered, observed, cells, parent, states) -> tuple[int, str | None, list[int]]:
    """Find the event for a detection. Return its number, its level before the detection,
    and the events that it absorbed.

    No near event: start a new event. Two or more near events: merge them into the oldest.
    """
    roots = set()
    for cell in covered:
        entry = cells.get(cell)
        if entry and abs(observed - entry[1]) <= WINDOW_S:
            roots.add(_find(parent, entry[0]))
    if not roots:
        parent.append(len(parent))
        states[len(parent) - 1] = _State()
        return len(parent) - 1, None, []
    oldest, *others = sorted(roots)
    before = _level(states[oldest])
    for other in others:
        parent[other] = oldest
        _absorb(states[oldest], states.pop(other))
    return oldest, before, others


def _find(parent: list[int], number: int) -> int:
    root = number
    while parent[root] != root:
        root = parent[root]
    while parent[number] != root:  # Make the next search short.
        parent[number], number = root, parent[number]
    return root


def _pass_time(detection: Detection, observed: float) -> float:
    return observed - observed % SCAN_S if detection.sensor_family == "abi" else observed


def _add_pass(passes: dict, key: tuple[str, str], time: float) -> None:
    """Add a time to the passes of one platform, unless it is part of a known pass.

    GOES times are scan starts, thus only an equal time is the same pass.
    """
    gap = 0.0 if key[0] == "abi" else PASS_GAP_S
    times = passes.setdefault(key, [])
    if all(abs(time - known) > gap for known in times):
        times.append(time)


def _add(state: _State, detection: Detection, observed: float) -> None:
    state.families.add(detection.sensor_family)
    key = (detection.sensor_family, detection.platform)
    _add_pass(state.passes, key, _pass_time(detection, observed))
    state.has_high |= detection.source_confidence == "high"
    state.count += 1
    state.first_observed = min(state.first_observed, observed)
    state.last_observed = max(state.last_observed, observed)
    state.first_available = min(state.first_available, detection.available_at.timestamp())
    state.sum_lat += detection.lat
    state.sum_lon += detection.lon
    box = state.box
    box[0], box[1] = min(box[0], detection.lat), min(box[1], detection.lon)
    box[2], box[3] = max(box[2], detection.lat), max(box[3], detection.lon)
    if detection.frp_mw is not None:
        state.max_frp_mw = max(state.max_frp_mw or 0.0, detection.frp_mw)


def _absorb(state: _State, other: _State) -> None:
    """Add the evidence of a newer event to the older event."""
    state.families |= other.families
    for key, times in other.passes.items():
        for time in times:
            _add_pass(state.passes, key, time)
    state.has_high |= other.has_high
    state.count += other.count
    state.first_observed = min(state.first_observed, other.first_observed)
    state.last_observed = max(state.last_observed, other.last_observed)
    state.first_available = min(state.first_available, other.first_available)
    state.sum_lat += other.sum_lat
    state.sum_lon += other.sum_lon
    state.box = [
        min(state.box[0], other.box[0]),
        min(state.box[1], other.box[1]),
        max(state.box[2], other.box[2]),
        max(state.box[3], other.box[3]),
    ]
    if other.max_frp_mw is not None:
        state.max_frp_mw = max(state.max_frp_mw or 0.0, other.max_frp_mw)


def _passes(state: _State) -> int:
    return sum(len(times) for times in state.passes.values())


def _families(state: _State) -> str:
    return "+".join(sorted(state.families))


def _level(state: _State) -> str:
    """HIGH: two or more sensor families. MEDIUM: a high source confidence, or two passes.
    LOW: one pass with low or nominal source confidence."""
    if len(state.families) >= 2:
        return "HIGH"
    return "MEDIUM" if state.has_high or _passes(state) >= 2 else "LOW"


def _event(event_id: int, state: _State) -> Event:
    return Event(
        id=event_id,
        first_observed_at=datetime.fromtimestamp(state.first_observed, UTC),
        last_observed_at=datetime.fromtimestamp(state.last_observed, UTC),
        first_available_at=datetime.fromtimestamp(state.first_available, UTC),
        detections=state.count,
        lat=state.sum_lat / state.count,
        lon=state.sum_lon / state.count,
        south=state.box[0],
        west=state.box[1],
        north=state.box[2],
        east=state.box[3],
        max_frp_mw=state.max_frp_mw,
        level=_level(state),
        families=_families(state),
        passes=_passes(state),
    )
