"""What the sensors could see at the place of an event: the GOES mask and the VIIRS passes.

The level and the rank of an event say how much evidence it has. This module says a different
thing: what the sensors saw at that place after the last detection. "Examined, no fire" and
"a pass with no detection" are not "the fire is out", but a brigade must know them.
Each answer uses only what we had at the as-of time.
"""

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from chispa import config
from chispa.sources import goes, passes
from chispa.store import to_text


def goes_view(lat: float, lon: float, as_of: datetime, raw_dir: Path) -> dict | None:
    """Return what GOES said for the place in the newest scan that we had at the as-of time.

    The recorded masks have one scan of each hour: we had one after the delay of a raw file.
    The live masks have each scan of the poller, with the time when the poller got it.
    The answer is None if the day of the as-of time and the day before have no such scan.
    """
    best = None
    for folder in (raw_dir / "goes_mask", raw_dir / "live" / "goes_mask"):
        for day in (as_of.date() - timedelta(days=1), as_of.date()):
            path = folder / str(day.year) / f"{day}.npz"
            if not path.exists():
                continue
            saved = np.load(path)
            scans = [datetime.fromisoformat(str(time)) for time in saved["times"]]
            had = [scan + config.GOES_RAW_DELAY for scan in scans]
            if "seen" in saved:
                had = [datetime.fromisoformat(str(time)) for time in saved["seen"]]
            for number, scan in enumerate(scans):
                if had[number] <= as_of and (best is None or scan > best[0]):
                    best = (scan, folder, saved["mask"][number])
    if best is None:
        return None
    place = np.load(best[1] / "grid.npz")
    nearest = ((place["lat"] - lat) ** 2 + (place["lon"] - lon) ** 2).argmin()
    row, col = np.unravel_index(nearest, place["lat"].shape)
    return {"scan_at": to_text(best[0]), "group": str(goes.mask_groups(best[2][row, col]))}


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
