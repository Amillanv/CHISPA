"""Tests of the events as they were at a time."""

from chispa.issued import Replay


def test_two_alerts_are_separate_before_their_merge_and_one_event_after():
    replay = Replay([(50.0, 2, 1)])
    replay.advance(49.0)
    assert (replay.ids(1), replay.ids(2), replay.root(2)) == ([1], [2], 2)
    replay.advance(50.0)
    assert (sorted(replay.ids(2)), replay.root(2)) == ([1, 2], 1)


def test_merges_in_a_chain_give_one_event():
    # 3 goes into 2, then 2 goes into 1. The merges are not in time sequence in the list.
    replay = Replay([(20.0, 2, 1), (10.0, 3, 2)])
    replay.advance(15.0)
    assert (sorted(replay.ids(3)), replay.ids(1)) == ([2, 3], [1])
    replay.advance(25.0)
    assert sorted(replay.ids(3)) == [1, 2, 3]
    assert replay.root(3) == 1


def test_alert_with_no_merge_is_its_own_event():
    replay = Replay([])
    replay.advance(100.0)
    assert (replay.ids(7), replay.root(7)) == ([7], 7)
