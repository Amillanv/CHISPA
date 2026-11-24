"""The first definition of the burn curve, which failed its hypothesis.

It joined the burned pixels of each image to a day. Each image adds its errors, thus more
images give more boxes with a false burn. A negative result has a table as a positive result:
this module makes that table for the last day of the curve. No other part uses this definition.
`docs/method.md` section 11.17 gives the hypotheses.
"""

from datetime import datetime, timedelta
from functools import partial
from pathlib import Path

from chispa import config, earthengine
from chispa.evaluation import burn, curve
from chispa.evaluation.report import share
from chispa.sources import sentinel2_ground

FIELDS = ("id", "settings", "clear_share", "burned_ha")


def _measure(target: dict) -> list[dict]:
    """Return the joined measure of one box at the last day of the curve, as one row."""
    box = burn.with_margin(*(float(target[name]) for name in ("south", "west", "north", "east")))
    first = datetime.fromisoformat(target["first_observed_at"])
    before, _ = burn.periods(first, datetime.fromisoformat(target["last_observed_at"]))
    period = (first, first + timedelta(days=max(config.CURVE_DAYS)))
    request = partial(sentinel2_ground.joined, box, before, period, curve.rule()[0])
    found = earthengine.again(request) or ("", "")
    values = dict(zip(FIELDS[2:], found, strict=True))
    return [{"id": target["id"], "settings": curve.signature(), **values}]


def measure(targets: list[dict], path: Path) -> None:
    """Measure each box that is not in the file, with the file rules of the burn curve."""
    curve.measure(targets, path, _measure, FIELDS)


def table(targets: list[dict], rows: list[dict], days: list[dict]) -> list[dict]:
    """Return, for each group, the joined definition at the last day against the curve.

    For each of the two: the boxes with an answer, and the boxes that it calls burned.
    """
    last = max(config.CURVE_DAYS)
    by_id = {
        "joined": {row["id"]: row for row in rows},
        "curve": {row["id"]: row for row in days if int(row["day"]) == last},
    }
    table_rows = []
    for group in (name for name in curve.LABELS if name in {t["group"] for t in targets}):
        ids = [str(target["id"]) for target in targets if target["group"] == group]
        row = {"group": curve.LABELS[group], "day": last, "boxes": len(ids)}
        for name, found in by_id.items():
            answers = [curve.answer(found[i]) for i in ids if i in found]
            clear = sum(answer is not None for answer in answers)
            row |= {f"{name}_answers": clear, f"{name}_burned": answers.count(True)}
            row[f"{name}_burned_share"] = share(answers.count(True), clear)
        table_rows.append(row)
    return table_rows
