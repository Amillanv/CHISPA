"""The burned pixels of the selected rule against the pixels of the annual map of burn scars.

The burn curve gives hectares, and a check with a person says only "burned" or "not burned".
This module measures, in each box of the burn check, the hectares of the rule, the hectares
of the map and the hectares that the two have. `docs/method.md` section 11.19 gives the rules.
"""

import csv
import hashlib
import statistics
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import ee
from scipy import stats

from chispa import config
from chispa.evaluation import burn, curve
from chispa.evaluation.report import share
from chispa.sources import scars, sentinel2_ground

FIELDS = ["id", "settings", "clear_ha", "rule_ha", "map_ha", "both_ha"]
SCALE_M = 30  # The pixel size of the map of burn scars.


def signature() -> str:
    """Return a short mark of each value that changes a measure of this module."""
    values = (curve.signature(), config.EVAL_MONTHS_BEFORE, SCALE_M)
    return hashlib.sha256(repr(values).encode()).hexdigest()[:8]


def months_of(first: datetime, last: datetime) -> list[int]:
    """Return the months of the map for an event: from its first detection to the months after
    its last detection, in the year of the first detection."""
    end = 12 if last.year > first.year else min(last.month + config.EVAL_MONTHS_BEFORE, 12)
    return list(range(first.month, end + 1))


def _measure(target: dict) -> dict:
    """Return the areas of one box, in hectares. With no view before the event: empty values."""
    outline = tuple(float(target[name]) for name in ("south", "west", "north", "east"))
    south, west, north, east = burn.with_margin(*outline)
    first = datetime.fromisoformat(target["first_observed_at"])
    last = datetime.fromisoformat(target["last_observed_at"])
    box = (south, west, north, east)
    marks = sentinel2_ground.rule_marks(box, *burn.periods(first, last), curve.rule()[0])
    row = {"id": target["id"], "settings": signature()}
    if marks is None:
        return {**row, **dict.fromkeys(FIELDS[2:], "")}
    mapped = scars.month_marks(first.year, months_of(first, last))
    clear, burned = marks.select("clear"), marks.select("burned")
    hectares = ee.Image.pixelArea().divide(10_000)
    bands = [
        hectares.updateMask(clear).rename("clear_ha"),
        hectares.updateMask(clear.And(burned)).rename("rule_ha"),
        hectares.updateMask(clear.And(mapped)).rename("map_ha"),
        hectares.updateMask(clear.And(burned).And(mapped)).rename("both_ha"),
    ]
    region = ee.Geometry.Rectangle([west, south, east, north])  # Earth Engine uses lon, lat.
    sums = ee.Image.cat(bands).reduceRegion(ee.Reducer.sum(), region, SCALE_M, maxPixels=1e10)
    return {**row, **{name: round(value, 2) for name, value in sums.getInfo().items()}}


def measure(targets: list[dict], path: Path) -> None:
    """Measure each target that is not in the file, and append it to the file.

    A file with different columns, or with measures of different values, stops the run.
    """
    old = burn.read(path) if path.exists() else []
    if old and (list(old[0]) != FIELDS or {row["settings"] for row in old} != {signature()}):
        raise RuntimeError(f"{path} has measures of different settings. Delete it, then run again.")
    done = {row["id"] for row in old}
    open_targets = [target for target in targets if str(target["id"]) not in done]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="") as file, ThreadPoolExecutor(max_workers=8) as workers:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        if not done:
            writer.writeheader()
        for row in workers.map(_measure, open_targets):
            writer.writerow(row)
            file.flush()


def table(targets: list[dict], rows: list[dict]) -> list[dict]:
    """Return, for each group, the areas of the rule and of the map and how well the two agree.

    `found_share` is the map area that the rule has also. `in_map_share` is the rule area that
    the map has also. The ratio is the rule hectares divided by the map hectares of a box,
    for the boxes where the map has the minimum area of the box rule or more.
    """
    by_id = {row["id"]: row for row in rows if row["clear_ha"] != ""}
    table_rows = []
    for group in (name for name in curve.LABELS if name in {target["group"] for target in targets}):
        own = [
            by_id[str(t["id"])] for t in targets if t["group"] == group and str(t["id"]) in by_id
        ]
        rule, mapped, both = (
            [float(row[name]) for row in own] for name in ("rule_ha", "map_ha", "both_ha")
        )
        ratios = [r / m for r, m in zip(rule, mapped, strict=True) if m >= config.BURN_HA_MIN]
        varied = len(set(rule)) > 1 and len(set(mapped)) > 1
        rank = stats.spearmanr(rule, mapped).statistic if varied else None
        table_rows.append(
            {
                "group": curve.LABELS[group],
                "boxes": len(own),
                "rule_ha": round(sum(rule)),
                "map_ha": round(sum(mapped)),
                "both_ha": round(sum(both)),
                "found_share": share(sum(both), sum(mapped)),
                "in_map_share": share(sum(both), sum(rule)),
                "rank_correlation": round(float(rank), 4) if rank is not None else None,
                "boxes_with_map": len(ratios),
                "ratio_median": round(statistics.median(ratios), 4) if ratios else None,
            }
        )
    return table_rows
