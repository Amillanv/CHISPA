"""Tests of the detections of an alert at a moment."""

import numpy as np

from chispa.evaluation.moments import at_moments


def test_alert_has_only_what_its_event_had_at_the_moment():
    # Alert 1 starts at 0 s. Alert 2 starts at 100 s. They merge at 500 s. One detection at 900 s.
    detections = {
        "issued": np.array([1, 2, 1, 1]),
        "available": np.array([0.0, 100.0, 500.0, 900.0]),
    }
    merges = [(500.0, 2, 1)]
    found = {
        (moment, alert): members.tolist()
        for moment, alert, _, members in at_moments(
            detections, merges, {"early": 50.0, "late": 450.0}
        )
    }
    assert found[("early", 1)] == [0]  # 50 s: only its first detection.
    assert found[("early", 2)] == [1]  # 150 s: alert 2 is separate.
    assert found[("late", 1)] == [0]  # 450 s: the merge did not occur.
    assert ("late", 2) not in found  # 550 s: alert 2 is a part of the event of alert 1.


def test_alert_gives_its_own_detections():
    detections = {"issued": np.array([1, 2, 1]), "available": np.array([0.0, 10.0, 20.0])}
    rows = list(at_moments(detections, [(20.0, 2, 1)], {"m": 5.0, "n": 100.0}))
    own = {(moment, alert): positions.tolist() for moment, alert, positions, _ in rows}
    assert own == {("m", 1): [0, 2], ("m", 2): [1], ("n", 1): [0, 2]}
    members = {(moment, alert): sorted(found.tolist()) for moment, alert, _, found in rows}
    assert members[("n", 1)] == [0, 1, 2]  # At 100 s the event of alert 1 holds alert 2.
