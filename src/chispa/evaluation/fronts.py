"""The answer of each front of one year, and the table of the answers.

A front is the pixels of one look that are adjacent (`fronts.py`). This module gives each front
its answer at 12 and at 24 hours: new ground, the front again with no new ground, a clear view
with no fire, or not visible. "No detection" is not "no fire": the GOES mask says if a place
was visible at the time of a later look. `docs/method.md` section 11.26 gives the rules.
"""

import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from chispa import config, fronts, view
from chispa.evaluation.report import percentile, share
from chispa.grid import pantanal_grid
from chispa.sources import border, goes

SOURCE = "firms"  # One product for each pass. INPE gives the same passes from a second processor.
ANSWERS = ("new_ground", "front_again", "clear_no_fire", "not_visible")
HIDDEN = ANSWERS.index("not_visible")
PIXEL_QUERY = """
SELECT CAST(strftime('%s', observed_at) AS INTEGER), lat, lon, frp_mw, platform,
       CAST(strftime('%s', available_at) AS INTEGER)
FROM detections
WHERE sensor_family = ? AND source = ? AND observed_at >= ? AND observed_at < ?
ORDER BY 1
"""


@dataclass(frozen=True)
class Masks:
    """The saved GOES masks and the mask pixel of each position. `days` keeps the days in use."""

    raw_dir: Path
    tree: cKDTree
    days: dict


def load_pixels(store: sqlite3.Connection, year: int) -> dict[str, np.ndarray]:
    """Return the VIIRS detections of FIRMS of one year in the box, in time sequence."""
    arguments = (fronts.SENSOR_FAMILY, SOURCE, f"{year}-01-01", f"{year + 1}-01-01")
    rows = store.execute(PIXEL_QUERY, arguments).fetchall()
    if not rows:
        raise RuntimeError(f"The store has no VIIRS detection of {year}. Run `chispa build`.")
    seconds, lat, lon, power, platform, available = zip(*rows, strict=True)
    seconds, lat, lon = np.array(seconds, dtype=float), np.array(lat), np.array(lon)
    return {
        "seconds": seconds,
        "available": np.array(available, dtype=float),
        "lat": lat,
        "lon": lon,
        "frp_mw": np.array([np.nan if value is None else value for value in power]),
        "platform": np.array(platform),
        "points": fronts.metres(lat, lon),
        "look": fronts.looks(seconds),
    }


def each_look(pixels: dict, since: float = -np.inf):
    """Give (first row, row after the last, look) for each look of the year, in time sequence.

    `since`: only the looks that started at or after this time. A live forecast needs only the
    newest looks, and to make each look of a year needs seconds.
    """
    first = np.searchsorted(pixels["look"], np.arange(pixels["look"].max() + 2))
    for a, b in zip(first[:-1], first[1:], strict=True):
        if pixels["seconds"][a] >= since:
            yield a, b, fronts.make_look(pixels["points"][a:b], pixels["points"][:a])


def open_masks(raw_dir: Path, year: int) -> Masks:
    """Return the masks of one year. A year that is complete must have the mask of its last day."""
    folder = raw_dir / "goes_mask"
    if year < datetime.now(UTC).year and not (folder / str(year) / f"{year}-12-31.npz").exists():
        raise RuntimeError(f"Run `chispa fetch goes_mask --year {year}` first.")
    place = np.load(folder / "grid.npz")
    return Masks(raw_dir, cKDTree(fronts.metres(place["lat"].ravel(), place["lon"].ravel())), {})


def _day_scans(masks: Masks, day: date) -> tuple[np.ndarray, np.ndarray]:
    """Return the scan times of one day in seconds, and the kind of each pixel in each scan:
    1 for an answer of GOES, 2 for the block-out zone of the sun, 0 for no answer."""
    if day not in masks.days:
        kinds = np.zeros(256, dtype=np.uint8)
        for name in view.ANSWERS:
            kinds[list(goes.MASK_GROUPS[name])] = 1
        kinds[list(goes.MASK_GROUPS["blocked"])] = 2
        path = masks.raw_dir / "goes_mask" / str(day.year) / f"{day}.npz"
        times, scans = np.empty(0), np.empty((0, masks.tree.n), dtype=np.uint8)
        saved = np.load(path) if path.exists() else {"times": []}
        if len(saved["times"]):  # A day with no file or with no scan: GOES gives no answer.
            starts = [datetime.fromisoformat(str(time)) for time in saved["times"]]
            times = np.array([start.timestamp() for start in starts])
            scans = kinds[saved["mask"]].reshape(len(times), -1)
        while len(masks.days) > 3:  # The looks come in time sequence: an old day has no more use.
            masks.days.pop(next(iter(masks.days)))
        masks.days[day] = (times, scans)
    return masks.days[day]


def examined(masks: Masks, at: float) -> np.ndarray:
    """Return True for each pixel of the mask window that GOES examined near the time `at`.

    The scan of a pixel is the nearest in time that is not in the block-out zone, and not farther
    than the limit in `config.py`. A pixel with no such scan, or with cloud in it, is False.
    """
    limit = config.FRONT_MASK_HOURS * 3600
    days = sorted({datetime.fromtimestamp(at + side * limit, UTC).date() for side in (-1, 1)})
    times, scans = zip(*(_day_scans(masks, day) for day in days), strict=True)
    times, scans = np.concatenate(times), np.concatenate(scans)
    seen = np.zeros(masks.tree.n, dtype=bool)
    near = np.nonzero(np.abs(times - at) <= limit)[0]
    for number in near[np.argsort(-np.abs(times[near] - at))]:  # The nearest scan is the last.
        seen = np.where(scans[number] != 2, scans[number] == 1, seen)
    return seen


def places(pixels: dict, bounds: tuple[int, int], look: fronts.Look) -> dict[str, np.ndarray]:
    """Return the start of the look, and the size and the centre of each front of the look.

    `complete_h` is the time from the start of the look to the moment when its last pixel was
    available: a forecast from the complete look cannot be earlier.
    """
    a, b = bounds
    size = np.bincount(look.labels, minlength=look.labels.max() + 1)
    rows = {"start": np.full(len(size), pixels["seconds"][a]), "pixels": size}
    complete_h = (pixels["available"][a:b].max() - pixels["seconds"][a]) / 3600
    rows["complete_h"] = np.full(len(size), complete_h)
    for name in ("lat", "lon"):
        rows[name] = np.bincount(look.labels, pixels[name][a:b], minlength=len(size)) / size
    return rows


def look_rows(pixels: dict, bounds: tuple[int, int], look: fronts.Look, masks: Masks) -> dict:
    """Return one row for each front of a look: its place, its size and its answers.

    A window of 24 hours has two times: 12 and 24 hours after the middle of the look. At each
    time the front was visible if it has a pixel again there, or if GOES examined its place.
    `examined` says only if GOES examined the place at each time: it does not read a later pixel.
    """
    a, b = bounds
    seconds, rows = pixels["seconds"], places(pixels, bounds, look)
    size, count = rows["pixels"], len(rows["pixels"])
    cells = masks.tree.query(look.points)[1]
    middle, before, hidden_before = float(np.median(seconds[a:b])), np.zeros(count), False
    seen = np.ones(count, dtype=bool)
    for hours, (low, high) in config.FRONT_WINDOWS_H.items():
        first = max(np.searchsorted(seconds, seconds[a] + low * 3600, side="right"), b)
        last = np.searchsorted(seconds, seconds[a] + high * 3600, side="right")
        found = fronts.answers(look, pixels["points"][first:last], config.FRONT_REACH_M[hours])
        dark = ~examined(masks, middle + hours * 3600)[cells]
        dark_share = np.bincount(look.labels, dark, minlength=count) / size
        seen = seen & (dark_share < config.FRONT_HIDDEN_SHARE)
        rows[f"examined_{hours}"] = seen
        hidden = ((found["again"] - before) == 0) & (dark_share >= config.FRONT_HIDDEN_SHARE)
        hidden_before = hidden | hidden_before
        choices = [found["new"] > 0, hidden_before, found["again"] > 0]
        rows[f"answer_{hours}"] = np.select(choices, [0, HIDDEN, 1], default=2)
        rows |= {f"{name}_{hours}": values for name, values in found.items()}
        before = found["again"]
    return rows


def front_rows(pixels: dict, masks: Masks, in_biome: np.ndarray) -> dict[str, np.ndarray]:
    """Return the rows of the fronts of one year: the fronts of the minimum size in the biome."""
    parts = []
    for a, b, look in each_look(pixels):
        rows = look_rows(pixels, (a, b), look, masks)
        keep = kept(rows, in_biome)
        parts.append({name: values[keep] for name, values in rows.items()})
    return {name: np.concatenate([part[name] for part in parts]) for name in parts[0]}


def counted(rows: dict, in_biome: np.ndarray) -> np.ndarray:
    """Return True for each front of a look with the minimum size and its centre in the biome."""
    keep = rows["pixels"] >= config.FRONT_MIN_PIXELS
    keep[keep] = in_biome[pantanal_grid().rows_cols(rows["lat"][keep], rows["lon"][keep])]
    return keep


def kept(rows: dict, in_biome: np.ndarray) -> np.ndarray:
    """Return True for each front of a look that counts in a result.

    It has the minimum size and its centre in the biome. Its look was complete before the first
    window starts. Its longest window ends in the year of the look, because the later pixels are
    those of that year, and before the end of the test year in progress (`config.py`).
    """
    first = min(low for low, _ in config.FRONT_WINDOWS_H.values())
    longest = max(high for _, high in config.FRONT_WINDOWS_H.values())
    year = datetime.fromtimestamp(float(rows["start"][0]), UTC).year
    end = datetime(year + 1, 1, 1, tzinfo=UTC).timestamp() - longest * 3600
    end = min(end, config.FRONT_TEST_END.timestamp())
    return counted(rows, in_biome) & (rows["start"] < end) & (rows["complete_h"] <= first)


def is_day_look(start: np.ndarray) -> np.ndarray:
    """Return True for each look that starts in the day hours of `config.py`."""
    low, high = config.FRONT_DAY_HOURS_UTC
    hour = (start % 86400) / 3600
    return (hour >= low) & (hour <= high)


def step_table(rows: dict[str, np.ndarray]) -> list[dict]:
    """Return the answers of the fronts for each window, for the day looks and the night looks.

    The share of the fronts with new ground is of the fronts that were visible. The two counts
    "not examined" are the fronts that have an answer only because a later pixel came.
    """
    day = is_day_look(rows["start"])
    table = []
    for hours in config.FRONT_WINDOWS_H:
        answer, new = rows[f"answer_{hours}"], rows[f"new_{hours}"]
        for label, part in (("day", day), ("night", ~day), ("all", np.ones(len(day), dtype=bool))):
            counts = [int((part & (answer == number)).sum()) for number in range(len(ANSWERS))]
            row = {"hours": hours, "looks": label, "fronts": int(part.sum())}
            row |= dict(zip(ANSWERS, counts, strict=True))
            row["new_ground_share"] = share(counts[0], int(part.sum()) - counts[HIDDEN])
            dark = part & ~rows[f"examined_{hours}"]
            row["new_ground_not_examined"] = int((dark & (answer == 0)).sum())
            row["front_again_not_examined"] = int((dark & (answer == 1)).sum())
            row["look_complete_h_median"] = percentile(rows["complete_h"][part], 50)
            row["fronts_with_10_new_pixels"] = int((part & (new >= 10)).sum())
            row["distance_m_median"] = percentile(rows[f"distance_m_{hours}"][part & (new > 0)], 50)
            table.append(row)
    return table


def step_tables(year: int, store_path: Path, raw_dir: Path) -> dict[str, list[dict]]:
    """Return the tables of the answers of one year: `front_steps` for the fronts that are not
    small, and `front_steps_small` for the small fronts (`config.py`)."""
    store = sqlite3.connect(store_path)
    rings = border.read_rings(raw_dir / "border" / "pantanal.geojson")
    in_biome = border.rasterize(rings, pantanal_grid())
    rows = front_rows(load_pixels(store, year), open_masks(raw_dir, year), in_biome)
    small = rows["pixels"] < config.FRONT_SMALL_BELOW
    parts = {"front_steps": ~small, "front_steps_small": small}
    return {
        name: step_table({key: values[part] for key, values in rows.items()})
        for name, part in parts.items()
    }
