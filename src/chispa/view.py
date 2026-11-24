"""What the sensors could see at the place of an event: the GOES mask and the VIIRS passes.

The level and the rank of an event say how much evidence it has. This module says a different
thing: what the sensors saw at that place after the last detection. "Examined, no fire" and
"a pass with no detection" are not "the fire is out", but a brigade must know them.
Each answer uses only what we had at the as-of time.
"""

from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from chispa import config
from chispa.sources import goes, passes
from chispa.store import to_text

# The group of a scan for the pixels of a place: the first group in this sequence that a pixel has.
# Thus "no_fire" says that GOES examined each pixel and found no fire.
PLACE_GROUPS = (
    "fire",
    "possible_fire",
    "cloud",
    "no_background",
    "blocked",
    "water",
    "not_processed",
    "no_fire",
)

# The answers of a run of scans. GOES examined the place only in these groups. The other groups
# (cloud, no background, blocked, water, not processed) are one answer: "not_seen".
ANSWERS = ("fire", "possible_fire", "no_fire")


def goes_view(
    lats: np.ndarray, lons: np.ndarray, last_seen: datetime, as_of: datetime, raw_dir: Path
) -> dict | None:
    """Return what GOES said for a place: in its newest scan, and in each scan after `last_seen`.

    The place is the GOES pixels of the positions, the detections of the newest passes of the event:
    the place of "last seen". `last_seen` is the newest observation of the event. `pixels` is the
    number of pixels of the place in the grid of the newest scan.
    `scans_after_last_detection` is the number of saved scans after it, and `after_last_detection`
    counts them in each group (`PLACE_GROUPS`). `runs_after_last_detection` gives them in time
    sequence (`_runs`). `newest_no_fire_at` is the newest of those scans in which GOES examined each
    pixel and found no fire: the last clear look. None: no such scan.
    The newest scan is from the day of the as-of time or the day before. If these days have no saved
    scan that we had at the as-of time, the answer is None: an older scan is not a view of now.
    """
    recent = as_of.date() - timedelta(days=1)
    seen = _place_scans(lats, lons, min(last_seen.date(), recent), as_of, raw_dir)
    newest = max((scan for scan in seen if scan.date() >= recent), default=None)
    if newest is None:
        return None
    after = {scan: group for scan, (group, _) in seen.items() if scan > last_seen}
    clear = [scan for scan, group in after.items() if group == "no_fire"]
    return {
        "pixels": seen[newest][1],
        "scan_at": to_text(newest),
        "group": seen[newest][0],
        "scans_after_last_detection": len(after),
        "after_last_detection": dict(Counter(after.values())),
        "runs_after_last_detection": _runs(after),
        "newest_no_fire_at": to_text(max(clear)) if clear else None,
    }


def _runs(groups: dict[datetime, str]) -> list[dict]:
    """Return the scans in time sequence, with the scans of one answer in a row as one run.

    A run has its first and last scan, its answer (`ANSWERS` or "not_seen"), the number of its
    scans and the number of its scans in each group. A fire that GOES sees in some scans and not
    in others gives a run for each change.
    """
    runs: list[dict] = []
    for scan in sorted(groups):
        group = groups[scan]
        answer = group if group in ANSWERS else "not_seen"
        if not runs or runs[-1]["answer"] != answer:
            runs.append(
                {"from": to_text(scan), "to": None, "answer": answer, "scans": 0, "groups": {}}
            )
        run = runs[-1]
        run["to"], run["scans"] = to_text(scan), run["scans"] + 1
        run["groups"][group] = run["groups"].get(group, 0) + 1
    return runs


def _place_scans(
    lats: np.ndarray, lons: np.ndarray, first: date, as_of: datetime, raw_dir: Path
) -> dict:
    """Return (group, pixels) of the place in each saved scan from `first` that we had at as-of.

    The recorded masks have one scan of each hour: we had one after the delay of a raw file.
    The live masks have each scan of the poller, with the time when the poller got it.
    The two have different grids: the number of pixels of the place is for the grid of the scan.
    """
    seen: dict[datetime, tuple[str, int]] = {}
    for folder in (raw_dir / "goes_mask", raw_dir / "live" / "goes_mask"):
        cells = None
        for number in range((as_of.date() - first).days + 1):
            day = first + timedelta(days=number)
            path = folder / str(day.year) / f"{day}.npz"
            if not path.exists():
                continue
            saved = np.load(path)
            if cells is None:
                cells = _cells(np.load(folder / "grid.npz"), lats, lons)
            scans = [datetime.fromisoformat(str(time)).astimezone(UTC) for time in saved["times"]]
            had = [scan + config.GOES_RAW_DELAY for scan in scans]
            if "seen" in saved:
                had = [datetime.fromisoformat(str(time)) for time in saved["seen"]]
            groups = goes.mask_groups(saved["mask"][:, cells[0], cells[1]])
            for scan, when, group in zip(scans, had, groups, strict=True):
                if when <= as_of:
                    place = min(group.tolist(), key=PLACE_GROUPS.index)
                    seen.setdefault(scan, (place, len(cells[0])))
    return seen


def _cells(place: np.lib.npyio.NpzFile, lats: np.ndarray, lons: np.ndarray) -> tuple:
    """Return the rows and columns of the grid pixels nearest to the positions, with no repeat.

    The distance is in a plane at the place: one degree of longitude is the cosine of the latitude
    times one degree of latitude. A position near the border of two pixels can go to either: the
    position of a detection has an error of the same size.
    """
    grid_lat, grid_lon = place["lat"], place["lon"]  # An archive gives a new copy at each read.
    scale = np.cos(np.deg2rad(float(np.mean(lats))))
    tree = cKDTree(np.column_stack([grid_lat.ravel(), grid_lon.ravel() * scale]))
    _, nearest = tree.query(np.unique(np.column_stack([lats, lons * scale]), axis=0))
    return np.unravel_index(np.unique(nearest), grid_lat.shape)


def passes_after(found: dict, as_of: datetime, raw_dir: Path) -> int | None:
    """Return the VIIRS passes over the event after its last detection. None: no pass list.

    Granules of one platform that are not farther apart than the pass gap are one pass.
    A granule is not counted if it is a part of the pass that gave the last detection.
    """
    try:
        granules = passes.read_year(as_of.year, raw_dir)
    except RuntimeError:
        return None
    gap_s = config.PASS_GAP.total_seconds()
    newest = int(found["observed"].argmax())
    last_s, last_platform = float(found["observed"][newest]), str(found["platform"][newest])
    lat, lon = float(found["lat"].mean()), float(found["lon"].mean())
    times: dict[str, list[float]] = {}
    for platform, time, outline in granules:
        same_pass = platform == last_platform and time <= last_s + gap_s
        after = last_s < time <= as_of.timestamp() and not same_pass
        if after and passes.covers(outline, lat, lon):
            times.setdefault(platform, []).append(time)
    return sum(1 + int((np.diff(sorted(seen)) > gap_s).sum()) for seen in times.values())
