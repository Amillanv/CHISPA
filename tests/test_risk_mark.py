"""Tests of the mark of an alert near an earlier alert, with cases small enough for paper."""

import numpy as np

from chispa.evaluation.risk_mark import mark_table, near_earlier, with_mark
from tests.test_fusion import KM

DAY = 86_400.0
# Four detections. The alert 1 is at the day 0. The alert 2 is 2 days later, 500 m to the
# north, and it has a second detection 300 m more to the north. The alert 3 is 50 km away.
DETECTIONS = {
    "lat": np.array([-17.5, -17.5 + 0.5 * KM, -17.5 + 0.8 * KM, -17.5 + 50 * KM]),
    "lon": np.full(4, -57.5),
    "available": np.array([0.0, 2 * DAY, 2 * DAY + 600, 2 * DAY]),
    "issued": np.array([1, 2, 2, 3]),
}


def row(alert: int, positions: list[int]) -> dict:
    return {"alert": alert, "positions": np.array(positions)}


def test_alert_has_the_mark_if_a_detection_of_an_earlier_alert_is_near(monkeypatch):
    monkeypatch.setattr("chispa.config.RISK_NEAR_EARLIER_M", 1000.0)
    monkeypatch.setattr("chispa.config.RISK_NEAR_EARLIER_DAYS", 14)
    rows = [row(1, [0]), row(2, [1, 2]), row(3, [3])]
    assert near_earlier(rows, DETECTIONS) == [False, True, False]
    # The detection of the alert 1 is in the event of the alert 2 at the moment: the two are
    # one event, and a detection of the event itself gives no mark.
    assert near_earlier([row(2, [0, 1, 2])], DETECTIONS) == [False]
    monkeypatch.setattr("chispa.config.RISK_NEAR_EARLIER_DAYS", 1)
    assert near_earlier(rows, DETECTIONS) == [False, False, False]
    monkeypatch.setattr("chispa.config.RISK_NEAR_EARLIER_DAYS", 14)
    monkeypatch.setattr("chispa.config.RISK_NEAR_EARLIER_M", 400.0)
    assert near_earlier(rows, DETECTIONS) == [False, False, False]


def alert(known: bool, near: bool, size_ha: float, only_inpe_goes: bool = False) -> dict:
    marks = {"known": known, "near_earlier": near, "only_inpe_goes": only_inpe_goes}
    return {"size_ha": size_ha} | marks


def test_table_compares_the_mark_with_the_mark_of_the_map(monkeypatch):
    monkeypatch.setattr("chispa.config.RISK_CLASS_LIMITS_HA", (10.0, 100.0))
    rows = [alert(True, True, 0.0)] * 3 + [alert(True, False, 0.0)]
    rows += [alert(False, True, 0.0), alert(False, True, 500.0), alert(False, False, 50.0)]
    rows += [alert(False, False, 500.0, only_inpe_goes=True)]
    found = mark_table({"0": rows})[0]
    assert (found["alerts"], found["known_fire_alerts"], found["near_earlier_alerts"]) == (8, 4, 5)
    # 3 of the 4 alerts on a known fire have the mark, and 3 of the 5 alerts with the mark are
    # on a known fire.
    assert (found["both"], found["recall"], found["precision"]) == (3, 0.75, 0.6)
    # An alert with only GOES rows of INPE gets no percentage: it is not a large alert here.
    assert (found["large_10ha"], found["large_10ha_near_earlier"]) == (2, 1)
    assert (found["large_100ha"], found["large_100ha_near_earlier"]) == (1, 1)
    # With the mark in the place of the mark of the map, the tables leave out the 5 alerts.
    marked = with_mark({"0": rows})["0"]
    assert sum(one["known"] for one in marked) == 5


def test_live_path_is_compared_with_the_rows_of_the_evaluation():
    from chispa.evaluation.risk_parity import _row

    def pair(x: float, live_x: float, near: bool = False) -> tuple[dict, dict]:
        row = {"inputs": {"x": x, "y": 1.0}, "near_earlier": near, "only_inpe_goes": False}
        return row, {"values": {"x": live_x, "y": 1.0}, "near_earlier": None, "no_percentage": None}

    # 4 alerts. One has no answer from the live path, one has a different x, and one has the
    # mark only in the evaluation.
    pairs = [pair(1.0, 1.0), pair(2.0, 2.5), pair(3.0, 3.0, near=True)]
    pairs.append(({"inputs": {"x": 0.0, "y": 0.0}}, {"no_answer": "not in the biome"}))
    found = _row("0", pairs, ["x", "y"])
    assert (found["alerts"], found["alerts_with_live_inputs"]) == (4, 3)
    assert (found["same_inputs"], found["same_marks"]) == (2, 2)
    assert (found["different_most"], found["different_most_alerts"]) == ("x", 1)
    assert found["different_most_largest"] == 0.5
