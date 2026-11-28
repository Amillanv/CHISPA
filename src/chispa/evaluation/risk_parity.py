"""A check that the live path gives an alert the inputs that the evaluation gave it.

The percentage of an alert has its test in the evaluation, and a live alert gets its inputs
from a different path: the store at the moment of the alert, and not the arrays of a year.
This module reads recorded alerts through the live path and compares each input and each mark
with those of the evaluation. It reads no outcome.
`docs/method.md` section 11.35 gives the rules.
"""

import sqlite3
from pathlib import Path

import numpy as np

from chispa import confidence, risk_live
from chispa.evaluation.confidence import MOMENTS

SAME = 1e-6  # Two values of an input are the same if they differ by less than this.


def _row(moment: str, pairs: list[tuple], names: list[str]) -> dict:
    """Return the table row of one moment from (row of the evaluation, alert of the live path)."""
    both = [(row, one) for row, one in pairs if "no_answer" not in one]
    gaps = np.array(
        [[abs(one["values"][name] - row["inputs"][name]) for name in names] for row, one in both]
    ).reshape(len(both), len(names))
    differs = (gaps >= SAME).sum(axis=0)
    worst = int(differs.argmax()) if len(both) else 0
    marks = [
        (one["near_earlier"] is not None) == row["near_earlier"]
        and (one["no_percentage"] == risk_live.ONLY_GOES) == row["only_inpe_goes"]
        for row, one in both
    ]
    some = bool(differs.any())
    return {
        "moment_h": moment,
        "alerts": len(pairs),
        "alerts_with_live_inputs": len(both),
        "same_inputs": int((gaps < SAME).all(axis=1).sum()),
        "same_marks": int(sum(marks)),
        "different_most": names[worst] if some else None,
        "different_most_alerts": int(differs[worst]) if some else 0,
        "different_most_largest": round(float(gaps[:, worst].max()), 6) if some else None,
    }


def parity_table(rows: dict[str, list], names: dict[str, list], paths: tuple[Path, Path]) -> list:
    """Return, for each moment, how many alerts get the same inputs and marks from the two paths.

    `rows` has the rows of the evaluation, and `names` the inputs of the models of each moment.
    `paths` has the store and the raw files. `different_most` is the input that differs for
    the most alerts, with its number of alerts and its largest difference.
    """
    store, table = sqlite3.connect(paths[0]), []
    for moment in MOMENTS:
        seconds = confidence.moment_seconds()[moment]
        waiting = [(row["alert"], moment, int(row["at"] - seconds)) for row in rows[moment]]
        read = risk_live.read_all(store, paths[1], waiting, None)
        table.append(_row(moment, list(zip(rows[moment], read, strict=True)), names[moment]))
    return table
