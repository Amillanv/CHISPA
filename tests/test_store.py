"""Tests of the SQLite store."""

import sqlite3
from dataclasses import replace
from datetime import timedelta

import pytest

from chispa.store import add_detections, open_store, read_detections
from tests.test_models import GOOD, NOON


def test_detection_is_the_same_after_save_and_read(tmp_path):
    store = open_store(tmp_path / "store.sqlite")
    add_detections(store, [GOOD])
    assert [d for _, d in read_detections(store, NOON, NOON + timedelta(days=1))] == [GOOD]


def test_second_save_of_the_same_detection_adds_no_row(tmp_path):
    store = open_store(tmp_path / "store.sqlite")
    assert add_detections(store, [GOOD]) == 1
    assert add_detections(store, [GOOD]) == 0


def test_read_uses_available_at_and_sorts_by_it(tmp_path):
    store = open_store(tmp_path / "store.sqlite")
    late = replace(GOOD, platform="NOAA20", available_at=NOON + timedelta(hours=5))
    add_detections(store, [late, GOOD])
    # GOOD was observed at noon but was available three hours later.
    assert list(read_detections(store, NOON, NOON + timedelta(hours=1))) == []
    assert [d for _, d in read_detections(store, NOON, NOON + timedelta(hours=6))] == [GOOD, late]


def test_store_of_an_older_version_stops_with_an_instruction(tmp_path):
    # A store from before the field `available_estimated`.
    old = sqlite3.connect(tmp_path / "old.sqlite")
    old.execute("CREATE TABLE detections (id INTEGER PRIMARY KEY, available_at TEXT NOT NULL)")
    old.close()
    with pytest.raises(RuntimeError, match="chispa build"):
        open_store(tmp_path / "old.sqlite")
