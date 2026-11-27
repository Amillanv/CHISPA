"""What the growth forecast says, in counts that a person can check.

A stated chance has a use only if it is near what comes: of 100 fronts with a stated chance of
70 percent, approximately 70 must get the answer yes. This module counts that for each band of
the stated chance. It also counts how frequently the most likely sectors of a front get its new
pixels, and it gives the scores for the first look of a fire apart.
It also gives apart the fronts that have no annual map of the year before.
`docs/method.md` section 11.28 gives the rules.
"""

from datetime import UTC, date, datetime

import numpy as np

from chispa import config
from chispa.evaluation import forecast
from chispa.evaluation.confidence import separation
from chispa.evaluation.report import share


def chance_rows(key: tuple[str, int], chance: np.ndarray, label: np.ndarray) -> list[dict]:
    """Return one row for each band of the stated chance of one question.

    A row has the rows of the band, their mean stated chance, and how many had the answer yes.
    A band has its lower limit and not its upper limit. The last band has the two.
    """
    limits = (0.0, *config.FORECAST_BANDS, 1.0)
    table = []
    for low, high in zip(limits[:-1], limits[1:], strict=True):
        part = (chance >= low) & ((chance < high) | (high == limits[-1]))
        came = int(label[part].sum())
        table.append(
            {
                "question": key[0],
                "hours": key[1],
                "chance_from": low,
                "chance_to": high,
                "rows": int(part.sum()),
                "chance_mean": round(float(chance[part].mean()), 4) if part.any() else None,
                "came": came,
                "came_share": share(came, int(part.sum())),
            }
        )
    return table


def sector_row(answers: dict, hours: int, use: np.ndarray, chance: np.ndarray) -> dict:
    """Return how frequently the most likely sectors of a front got its new pixels.

    The fronts are those with a row (`use`) and the minimum number of new pixels for a direction.
    `sector_by_chance` is the share of all sectors of those fronts that got a new pixel.
    """
    pixels = answers[f"sectors_{hours}"][use]
    many = pixels.sum(axis=1) >= config.FRONT_DIRECTION_PIXELS
    pixels = pixels[many]
    likely = np.argsort(-chance.reshape(-1, config.FRONT_SECTORS)[many], axis=1, kind="stable")
    row = {"hours": hours, "fronts": int(many.sum()), "new_pixels": int(pixels.sum())}
    row["sector_by_chance"] = share(int((pixels > 0).sum()), pixels.size)
    for top in config.FORECAST_TOP_SECTORS:
        chosen = np.take_along_axis(pixels, likely[:, :top], axis=1)
        row[f"top_{top}_fronts"] = int((chosen.sum(axis=1) > 0).sum())
        row[f"top_{top}_pixels"] = int(chosen.sum())
    return row


def _score(hours: int, name: str, part: np.ndarray, found: dict) -> dict:
    """Return the scores of the trees for the fronts of `part`. `chance_sum` is the number of
    fronts with new ground that the stated chances expect."""
    new, chance = found["new"][part], found["chance"][part]
    many = part & (found["new"] >= config.FRONT_DIRECTION_PIXELS)
    return {
        "hours": hours,
        "fronts": name,
        "rows": int(part.sum()),
        "new_ground": int((new > 0).sum()),
        "chance_sum": round(float(chance.sum()), 1),
        "auc_trees": separation(chance, (new > 0).astype(float)),
        "fronts_with_direction": int(many.sum()),
        "trees_in_45": forecast.in_45(found["guess"], found["truth"], many),
    }


def first_look_rows(rows: dict, hours: int, use: np.ndarray, trees: dict) -> list[dict]:
    """Return the scores of the trees for the first look of a fire, and for the other fronts.

    A front is the first look of a fire if each of its pixels is farther than the largest reach
    from each pixel that we knew before. `use` is True for each front with a row, and `trees`
    has the chances of the questions for those fronts.
    """
    found = _found(rows, hours, use, trees)
    first = rows["inputs"]["first_look"][use]
    return [
        _score(hours, name, part, found)
        for name, part in (("first look", first), ("other", ~first))
    ]


def _found(rows: dict, hours: int, use: np.ndarray, trees: dict) -> dict:
    """Return what `_score` needs for the fronts with a row: the answers and what the trees say."""
    answers = rows["answers"]
    found = {"new": answers[f"new_{hours}"][use], "chance": trees["new_ground"]}
    found["truth"] = answers[f"direction_deg_{hours}"][use]
    return found | {"guess": forecast.directions(trees["sector"])}


def period_rows(rows: dict, hours: int, use: np.ndarray, trees: dict) -> list[dict]:
    """Return the scores of the trees and of two baselines for the fronts of a year before the
    month in which the annual map of the year before comes (`config.py`), and for the others.

    A front before that month has no value for the inputs from that map (`docs/method.md`
    section 11.31). The two groups have the name of that day: the calendar makes them, not
    the map on disk. `trees` also has the persistence value of each front.
    """
    found = _found(rows, hours, use, trees)
    wind = rows["inputs"]["wind_direction_deg"][use]
    starts = rows["answers"]["start"][use]
    month = np.array([datetime.fromtimestamp(float(start), UTC).month for start in starts])
    early = month < config.FRONT_LAST_YEAR_FROM_MONTH
    day, table = f"1 {date(2000, config.FRONT_LAST_YEAR_FROM_MONTH, 1):%B}", []
    for name, part in ((f"before {day}", early), (f"from {day}", ~early)):
        row = _score(hours, name, part, found)
        label = (found["new"][part] > 0).astype(float)
        many = part & (found["new"] >= config.FRONT_DIRECTION_PIXELS)
        row["auc_persistence"] = separation(trees["persistence"][part], label)
        table.append(row | {"wind_in_45": forecast.in_45(wind, found["truth"], many)})
    return table
