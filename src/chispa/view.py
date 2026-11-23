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

from chispa import config
from chispa.sources import goes, passes
from chispa.store import to_text


def goes_view(
    lat: float, lon: float, last_seen: datetime, as_of: datetime, raw_dir: Path
) -> dict | None:
    """Return what GOES said for the place: in its newest scan, and in each scan after `last_seen`.

    `last_seen` is the newest observation of the event. `after_last_detection` counts the scans
    after it in each mask group. `newest_no_fire_at` is the newest of those scans in which GOES
    examined the place and found no fire: the last clear look. None: no such scan.
    The answer is None if no saved scan that we had at the as-of time is near that time.
    """
    first = min(last_seen.date(), as_of.date() - timedelta(days=1))
    seen = _place_scans(lat, lon, first, as_of, raw_dir)
    if not seen:
        return None
    after = {scan: group for scan, group in seen.items() if scan > last_seen}
    clear = [scan for scan, group in after.items() if group == "no_fire"]
    return {
        "scan_at": to_text(max(seen)),
        "group": seen[max(seen)],
        "after_last_detection": dict(Counter(after.values())),
        "newest_no_fire_at": to_text(max(clear)) if clear else None,
    }


def _place_scans(lat: float, lon: float, first: date, as_of: datetime, raw_dir: Path) -> dict:
    """Return the mask group of the place in each saved scan from `first` that we had at as-of.

    The recorded masks have one scan of each hour: we had one after the delay of a raw file.
    The live masks have each scan of the poller, with the time when the poller got it.
    """
    seen: dict[datetime, str] = {}
    for folder in (raw_dir / "goes_mask", raw_dir / "live" / "goes_mask"):
        cell = None
        for number in range((as_of.date() - first).days + 1):
            day = first + timedelta(days=number)
            path = folder / str(day.year) / f"{day}.npz"
            if not path.exists():
                continue
            saved = np.load(path)
            if cell is None:
                place = np.load(folder / "grid.npz")
                nearest = ((place["lat"] - lat) ** 2 + (place["lon"] - lon) ** 2).argmin()
                cell = np.unravel_index(nearest, place["lat"].shape)
            scans = [datetime.fromisoformat(str(time)).astimezone(UTC) for time in saved["times"]]
            had = [scan + config.GOES_RAW_DELAY for scan in scans]
            if "seen" in saved:
                had = [datetime.fromisoformat(str(time)) for time in saved["seen"]]
            groups = goes.mask_groups(saved["mask"][:, cell[0], cell[1]])
            for scan, when, group in zip(scans, had, groups, strict=True):
                if when <= as_of:
                    seen.setdefault(scan, str(group))
    return seen


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
