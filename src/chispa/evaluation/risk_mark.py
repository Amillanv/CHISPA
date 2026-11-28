"""The mark of an alert near an earlier alert, against the mark of the map.

The models of the growth risk are for an alert with a new fire. The map of a year says which
alerts are on a known fire, and a live alert does not have that map. A live alert has the
detections: this module gives each recorded alert the mark that a live alert gets
(`risk_live.near_earlier`), and it compares that mark with the mark of the map.
`docs/method.md` section 11.35 gives the rules and the hypotheses.
"""

import numpy as np

from chispa import config
from chispa.evaluation.match import Fields
from chispa.evaluation.report import share
from chispa.risk import DAY_S, distance_m


def near_earlier(rows: list[dict], detections: Fields) -> list[bool]:
    """Return, for each row, True if its alert is near a detection of an earlier alert.

    A detection counts if it was available before the first detection of the alert and not
    more than some days before it, and if it is not in the event of the alert at the moment.
    `config.py` has the days and the distance.
    """
    available = detections["available"].astype(float)
    order = np.argsort(available, kind="stable")
    ordered, lat, lon = available[order], detections["lat"], detections["lon"]
    reach = config.RISK_NEAR_EARLIER_M / 100_000  # In degrees: more than the distance.
    marks = []
    for row in rows:
        positions = row["positions"]
        start = available[positions[detections["issued"][positions] == row["alert"]]].min()
        window = start - config.RISK_NEAR_EARLIER_DAYS * DAY_S
        others = order[slice(*np.searchsorted(ordered, [window, start], side="left"))]
        in_box = lat[others] >= lat[positions].min() - reach
        in_box &= lat[others] <= lat[positions].max() + reach
        in_box &= lon[others] >= lon[positions].min() - reach
        in_box &= lon[others] <= lon[positions].max() + reach
        others = others[in_box]
        others = others[~np.isin(others, positions)]
        own = (lat[positions], lon[positions])
        near = len(others) and distance_m(own, (lat[others], lon[others])).min()
        marks.append(bool(len(others)) and bool(near <= config.RISK_NEAR_EARLIER_M))
    return marks


def with_mark(rows: dict[str, list]) -> dict[str, list]:
    """Return the rows of each moment with the mark of the detections in the place of the mark
    of the map: an alert near an earlier alert is then the alert that the tables leave out."""
    return {m: [row | {"known": row["near_earlier"]} for row in found] for m, found in rows.items()}


def no_mark(rows: dict[str, list]) -> dict[str, list]:
    """Return the rows of each moment with no alert left out for a fire that an earlier alert
    saw: the baseline of the mark."""
    return {m: [row | {"known": False} for row in found] for m, found in rows.items()}


def mark_table(rows: dict[str, list]) -> list[dict]:
    """Return, for each moment of one year, the mark of the detections against that of the map.

    The recall is the share of the alerts on a known fire that have the mark. The precision
    is the share of the alerts with the mark that are on a known fire. The last columns are for
    the alerts that get a percentage with the mark of the map: not on a known fire, and not
    with only GOES rows of INPE. They give how many of them became large for each limit, and
    how many of those have the mark: the live path gives them no percentage.
    """
    table = []
    for moment, of_moment in rows.items():
        # A moment with no alert gives arrays with no value: they must be arrays of marks.
        known = np.array([row["known"] for row in of_moment], dtype=bool)
        near = np.array([row["near_earlier"] for row in of_moment], dtype=bool)
        size = np.array([row["size_ha"] for row in of_moment], dtype=float)
        counted = ~known & ~np.array([row["only_inpe_goes"] for row in of_moment], dtype=bool)
        found = {
            "moment_h": moment,
            "alerts": len(known),
            "known_fire_alerts": int(known.sum()),
            "near_earlier_alerts": int(near.sum()),
            "both": int((known & near).sum()),
            "recall": share((known & near).sum(), known.sum()),
            "precision": share((known & near).sum(), near.sum()),
        }
        for limit in config.RISK_CLASS_LIMITS_HA:
            large = counted & (size >= limit)
            found[f"large_{limit:g}ha"] = int(large.sum())
            found[f"large_{limit:g}ha_near_earlier"] = int((large & near).sum())
        table.append(found)
    return table
