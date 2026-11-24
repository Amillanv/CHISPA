"""Tests of what the sensors could see at the place of an event: VIIRS passes and GOES masks."""

from datetime import UTC, datetime, timedelta

import numpy as np

from chispa import view
from tests.test_fusion import T0

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


def save(folder, lat, lon, scans, mask, seen=True):
    """Save a grid and the masks of one day. A live mask has the time when the poller got it."""
    (folder / str(T0.year)).mkdir(parents=True)
    np.savez(folder / "grid.npz", lat=np.array([lat]), lon=np.array([lon]))
    times = np.array([scan.isoformat() for scan in scans])
    extra = {"seen": times} if seen else {}
    np.savez(folder / str(T0.year) / f"{T0.date()}.npz", times=times, mask=np.array(mask), **extra)


def hours(*values):
    return [T0 + timedelta(hours=value) for value in values]


def test_goes_view_needs_each_pixel_of_the_newest_detections_for_a_clear_look(tmp_path):
    # Three pixels. The newest pass has three detections: two in the first pixel, one in the second.
    # The third pixel is far away and has no detection.
    # Scans after the detection: both no fire; one cloud; one possible fire; no fire again.
    mask = [[[100, 100, 30]], [[100, 200, 100]], [[13, 100, 100]], [[100, 100, 200]]]
    save(
        tmp_path / "live" / "goes_mask",
        [-17.5] * 3,
        [-57.5, -57.48, -50.0],
        hours(1, 2, 3, 4),
        mask,
    )
    positions = np.array([-17.5, -17.5, -17.5]), np.array([-57.5, -57.501, -57.48])
    found = view.goes_view(*positions, T0, T0 + timedelta(hours=5), tmp_path)
    # The fire at the third pixel is not this place. A cloud or a possible fire at one pixel is
    # not a clear look: the last clear look is the scan of 4 hours.
    assert found == {
        "pixels": 2,
        "scan_at": (T0 + timedelta(hours=4)).isoformat(),
        "group": "no_fire",
        "scans_after_last_detection": 4,
        "after_last_detection": {"no_fire": 2, "cloud": 1, "possible_fire": 1},
        "runs_after_last_detection": found["runs_after_last_detection"],
        "newest_no_fire_at": (T0 + timedelta(hours=4)).isoformat(),
    }
    answers = [(run["answer"], run["scans"]) for run in found["runs_after_last_detection"]]
    assert answers == [("no_fire", 1), ("not_seen", 1), ("possible_fire", 1), ("no_fire", 1)]


def test_runs_give_the_scans_in_time_with_one_row_for_each_answer(tmp_path):
    # One pixel. After the detection: cloud, no background, two possible fire, no fire, cloud.
    mask = [[[200]], [[170]], [[13]], [[33]], [[100]], [[205]]]
    save(tmp_path / "live" / "goes_mask", [-17.5], [-57.5], hours(1, 2, 3, 4, 5, 6), mask)
    found = view.goes_view(
        np.array([-17.5]), np.array([-57.5]), T0, T0 + timedelta(hours=7), tmp_path
    )
    at = [(T0 + timedelta(hours=hour)).isoformat() for hour in range(7)]
    # Cloud and no background are one answer: GOES could not see the place. A run keeps its groups.
    assert found["runs_after_last_detection"] == [
        {
            "from": at[1],
            "to": at[2],
            "answer": "not_seen",
            "scans": 2,
            "groups": {"cloud": 1, "no_background": 1},
        },
        {
            "from": at[3],
            "to": at[4],
            "answer": "possible_fire",
            "scans": 2,
            "groups": {"possible_fire": 2},
        },
        {"from": at[5], "to": at[5], "answer": "no_fire", "scans": 1, "groups": {"no_fire": 1}},
        {"from": at[6], "to": at[6], "answer": "not_seen", "scans": 1, "groups": {"cloud": 1}},
    ]


def test_a_position_goes_to_the_pixel_with_the_nearest_centre_in_kilometres(tmp_path):
    # The first centre is 0.0098 degrees to the north, the second 0.01 degrees to the east.
    # At 17 degrees south, 0.01 degrees of longitude is 0.0096 degrees of latitude: east is nearer.
    save(
        tmp_path / "live" / "goes_mask",
        [-16.9902, -17.0],
        [-57.0, -56.99],
        hours(1),
        [[[200, 100]]],
    )
    found = view.goes_view(
        np.array([-17.0]), np.array([-57.0]), T0, T0 + timedelta(hours=2), tmp_path
    )
    assert (found["pixels"], found["group"]) == (1, "no_fire")


def test_the_number_of_pixels_is_for_the_grid_of_the_newest_scan(tmp_path):
    # In the recorded grid the two detections are in two pixels. In the live grid they are in one.
    save(
        tmp_path / "goes_mask",
        [-17.5, -17.5],
        [-57.5, -57.49],
        hours(1),
        [[[100, 200]]],
        seen=False,
    )
    save(tmp_path / "live" / "goes_mask", [-17.5], [-57.5], hours(2), [[[100]]])
    positions = np.array([-17.5, -17.5]), np.array([-57.5, -57.49])
    found = view.goes_view(*positions, T0, T0 + timedelta(hours=3), tmp_path)
    assert (found["pixels"], found["group"]) == (1, "no_fire")
    assert found["after_last_detection"] == {"cloud": 1, "no_fire": 1}
