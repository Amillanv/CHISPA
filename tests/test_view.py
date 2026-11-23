"""Tests of what the sensors could see at the place of an event."""

from datetime import UTC, datetime, timedelta

import numpy as np

from chispa import view

BOX = np.array([[-18.0, -58.0], [-18.0, -57.0], [-17.0, -57.0], [-17.0, -58.0], [-18.0, -58.0]])
FAR = BOX + 5.0


def test_passes_after_the_last_detection_are_counted_one_time_for_each_pass(monkeypatch, tmp_path):
    monkeypatch.setattr("chispa.config.PASS_GAP", timedelta(minutes=30))
    granules = [
        ("NOAA20", 100.0, BOX),  # The pass that gave the last detection: not counted.
        ("NOAA21", 3000.0, BOX),  # A pass of a different satellite: counted.
        ("NOAA21", 3360.0, BOX),  # The next granule of that pass: not counted again.
        ("NOAA20", 9000.0, BOX),  # A new pass of the first satellite: counted.
        ("NOAA21", 9500.0, FAR),  # This pass does not cover the event.
        ("NOAA21", 99000.0, BOX),  # After the as-of time.
    ]
    monkeypatch.setattr("chispa.sources.passes.read_year", lambda year, raw_dir: granules)
    found = {
        "observed": np.array([50.0, 90.0]),
        "platform": np.array(["SNPP", "NOAA20"]),
        "lat": np.array([-17.5, -17.5]),
        "lon": np.array([-57.5, -57.5]),
    }
    as_of = datetime.fromtimestamp(20000, UTC)
    assert view.passes_after(found, as_of, tmp_path) == 2


def test_no_pass_list_gives_no_count(tmp_path):
    found = {"observed": np.array([50.0]), "platform": np.array(["SNPP"])}
    found |= {"lat": np.array([-17.5]), "lon": np.array([-57.5])}
    assert view.passes_after(found, datetime.fromtimestamp(20000, UTC), tmp_path) is None
