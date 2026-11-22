"""Tests of the severity and of its check, with cases small enough for paper."""

import numpy as np

from chispa import severity
from chispa.evaluation.severity import inputs_table, outcomes, rank_table, score_table
from chispa.grid import Grid

# A layer grid of 4 by 4 cells of one degree. Row 0 is the north edge at latitude 4.
GRID = Grid(west=0.0, north=4.0, pixel_deg=1.0, width=4, height=4)


def layers():
    cover = np.full((4, 4), 15, dtype=np.uint8)  # pasture
    cover[0, :] = 3  # forest in the north row
    people_near = np.zeros((4, 4))
    people_near[0, 0] = 500.0
    distance = {"indigenous": np.full((4, 4), 50.0), "protected": np.full((4, 4), 30.0)}
    distance["indigenous"][0, 0] = 0.0
    nearest = {"indigenous": np.full((4, 4), 7), "protected": np.full((4, 4), 9)}
    return severity.Layers(GRID, cover, people_near, distance, nearest, {7: "Land A", 9: "Park B"})


def set_steps(monkeypatch):
    monkeypatch.setattr("chispa.config.SEVERITY_POWER_STEPS_MW", (10.0, 50.0, 100.0))
    monkeypatch.setattr("chispa.config.SEVERITY_EXTENT_STEPS_KM", (1.0, 5.0, 20.0))
    monkeypatch.setattr("chispa.config.SEVERITY_ADVANCE_STEPS_M", (1000.0, 2000.0, 4000.0))
    monkeypatch.setattr("chispa.config.SEVERITY_PEOPLE_STEPS", (10.0, 100.0, 1000.0))


def test_value_gets_an_equal_part_of_the_points_for_each_step():
    assert severity.step_points(60.0, (10.0, 50.0, 100.0), 30) == 20.0
    assert severity.step_points(5.0, (10.0, 50.0, 100.0), 30) == 0.0
    assert severity.step_points(None, (10.0, 50.0, 100.0), 30) == 0.0
    assert severity.step_points(60.0, None, 30) == 0.0


def test_facts_come_from_the_detections_and_the_layers():
    # Two detections in the north row: one in the cell with people and indigenous land.
    lat, lon = np.array([3.5, 3.5]), np.array([0.5, 1.5])
    found = severity.facts(lat, lon, np.array([np.nan, 60.0]), 1500.0, layers())
    assert (found["detections"], found["max_frp_mw"], found["advance_m"]) == (2, 60.0, 1500.0)
    assert (found["cover"], found["cover_share"], found["people_near"]) == ("forest", 1.0, 500.0)
    assert (found["indigenous_km"], found["indigenous_name"]) == (0.0, "Land A")
    assert (found["protected_km"], found["protected_name"]) == (30.0, "Park B")
    assert round(found["extent_km"]) == 111


def test_detection_with_no_fire_power_gives_no_value():
    found = severity.facts(np.array([1.5]), np.array([1.5]), np.array([np.nan]), None, layers())
    assert (found["max_frp_mw"], found["cover"], found["extent_km"]) == (None, "pasture", 0.0)


def test_severity_is_the_sum_of_the_points_of_its_parts(monkeypatch):
    set_steps(monkeypatch)
    lat, lon = np.array([3.5, 3.5]), np.array([0.5, 1.5])
    found = severity.facts(lat, lon, np.array([np.nan, 60.0]), 1500.0, layers())
    total, parts = severity.score(found)
    # Power 60 MW: 2 of 3 steps of 20. Extent 111 km: 3 of 3 of 15. Advance 1500 m: 1 of 3 of 15.
    # Forest: 20. People 500: 2 of 3 of 15. In indigenous land: 15.
    wanted = {
        "power": 13.33,
        "extent": 15.0,
        "advance": 5.0,
        "cover": 20.0,
        "people": 10.0,
        "land": 15.0,
    }
    assert {name: round(value, 2) for name, value in parts.items()} == wanted
    assert round(total, 2) == 78.33


def test_land_that_is_near_gets_a_part_of_the_points(monkeypatch):
    set_steps(monkeypatch)
    monkeypatch.setattr("chispa.config.SEVERITY_NEAR_KM", 5.0)
    found = severity.facts(np.array([1.5]), np.array([1.5]), np.array([1.0]), None, layers())
    assert severity.score(found)[1]["land"] == 0.0
    found["protected_km"] = 4.0
    assert severity.score(found)[1]["land"] == 8.0


def test_outcome_is_the_area_of_the_counted_fires_of_an_event():
    detections = {"event": np.array([1, 1, 2, 3])}
    pairs = (
        np.array([0, 1, 1, 2]),
        np.array([1, 1, 2, 3]),
    )  # Event 1: fires 1 and 2. Event 2: fire 3.
    fires = {
        "area_ha": np.array([0.0, 100.0, 50.0, 5.0]),
        "counted": np.array([False, True, True, False]),
    }
    assert outcomes(detections, pairs, fires) == {1: 150.0}


def event(score, area_ha, detections=1):
    return {
        "severity": score,
        "area_ha": area_ha,
        "detections": detections,
        "max_frp_mw": score * 2 if score > 50 else None,
        "extent_km": score / 10,
        "advance_m": None,
    }


def test_tables_of_the_severity(monkeypatch):
    monkeypatch.setattr("chispa.config.SEVERITY_SCORE_CLASSES", (0.0, 50.0, 100.1))
    rows = [event(10.0, 0.0, 3), event(20.0, 40.0, 1), event(60.0, 100.0, 2), event(90.0, 900.0, 4)]
    low, high, everything = score_table(rows)
    assert (low["events"], low["events_matched"], low["matched_share"], low["area_ha_median"]) == (
        2,
        1,
        0.5,
        40.0,
    )
    assert (high["events"], high["events_matched"], high["area_ha_median"]) == (2, 2, 500.0)
    assert everything["events"] == 4
    by_name = {row["measure"]: row for row in rank_table(rows)}
    assert by_name["severity"]["rank_correlation"] == 1.0
    assert by_name["detections"]["rank_correlation"] == 0.4
    power, extent, advance = inputs_table(rows)
    assert (power["events"], power["events_with_a_value"], power["p50"]) == (4, 2, 150.0)
    assert (advance["events_with_a_value"], advance["p50"]) == (0, None)
