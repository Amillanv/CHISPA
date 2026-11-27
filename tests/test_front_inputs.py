"""Tests of the inputs of a front, with cases small enough for paper."""

from datetime import UTC, date, datetime

import numpy as np
import pytest

from chispa import fronts
from chispa.evaluation import front_inputs
from chispa.grid import layer_grid
from chispa.sources import weather

ROW = np.array([[0.0, 0.0], [0.0, 400.0], [0.0, 800.0]])  # Three pixels in a row to the east.
NORTH, EAST, SOUTH, WEST = 0, 2, 4, 6


@pytest.fixture(autouse=True)
def fixed_values(monkeypatch):
    monkeypatch.setattr("chispa.config.FRONT_LINK_M", 1500.0)
    monkeypatch.setattr("chispa.config.FRONT_REACH_M", {12: 5000.0, 24: 8000.0})
    monkeypatch.setattr("chispa.config.FRONT_SECTORS", 8)
    monkeypatch.setattr("chispa.config.GROWTH_FLOOR_M", 850.0)
    monkeypatch.setattr("chispa.config.GROWTH_ADVANCE_PERCENT", 90)
    monkeypatch.setattr("chispa.config.FRONT_WEATHER_DAYS", 3)
    monkeypatch.setattr("chispa.config.FRONT_RAIN_DAYS", (7, 30))
    monkeypatch.setattr("chispa.config.FRONT_WIND_BLOCKS", 2)


def test_the_shape_gives_the_reach_to_each_sector_and_the_hot_side():
    look = fronts.make_look(ROW, np.empty((0, 2)))
    inputs, centre, reach = front_inputs.shape_inputs(look, np.array([1.0, 1.0, 4.0]))
    assert centre.tolist() == [[0.0, 400.0]]
    assert (reach[0, EAST], reach[0, WEST], reach[0, NORTH]) == pytest.approx((400.0, 400.0, 0.0))
    assert inputs["log_pixels"][0] == pytest.approx(np.log1p(3))
    assert inputs["log_frp_mean"][0] == pytest.approx(np.log1p(2.0))
    # The fire power is at -400 m, 0 m and 400 m from the centre: (-400 + 1600) / 6 = 200 m east.
    assert inputs["heat_km_s"][0, EAST] == pytest.approx(0.2)
    assert inputs["heat_km_s"][0, WEST] == pytest.approx(-0.2)


def test_the_pixels_on_new_ground_say_how_the_front_came():
    # One known pixel. The look has a pixel on it, two pixels to the east past the floor,
    # and one pixel 30 km away: a new fire.
    points = np.array([[0.0, 0.0], [0.0, 1000.0], [0.0, 1400.0], [0.0, 30_000.0]])
    inputs = front_inputs.came_inputs(fronts.make_look(points, np.array([[0.0, 0.0]])))
    assert inputs["log_came"].tolist() == pytest.approx([np.log1p(2), 0.0])
    assert inputs["came_share"].tolist() == pytest.approx([2 / 3, 0.0])
    assert inputs["log_fresh"].tolist() == pytest.approx([0.0, np.log1p(1)])
    assert (inputs["came_share_s"][0, EAST], inputs["came_adjacent_s"][0, EAST + 1]) == (1.0, 1.0)
    assert (inputs["came_direction_deg"][0], inputs["came_steady"][0]) == pytest.approx((90.0, 1.0))
    assert np.isnan(inputs["came_direction_deg"][1])


def test_the_known_pixels_around_a_front_have_a_sector_and_a_ring():
    # 500 m west of the row: at the front. 3 km north of its last pixel: farther. 20 km: none.
    before = np.array([[0.0, -500.0], [3000.0, 800.0], [0.0, 20_000.0]])
    inputs = front_inputs.older_inputs(fronts.make_look(ROW, before))
    assert inputs["log_older_near_s"][0, WEST] == pytest.approx(np.log1p(1))
    assert inputs["log_older_far_s"][0, NORTH] == pytest.approx(np.log1p(1))
    assert inputs["older_near_share_s"][0, WEST] == 1.0
    assert inputs["log_older_behind_s"][0, EAST] == pytest.approx(np.log1p(1))
    assert (inputs["log_older_near"][0], inputs["log_older_far"][0]) == pytest.approx(
        [np.log1p(1)] * 2
    )


def layers_of(days: int) -> front_inputs.Layers:
    """Layers with grassland in each cell, a burn in each cell last year, and a wind to the east."""
    grid, cells = layer_grid(), weather.weather_grid()
    number = list(front_inputs.config.COVER_GROUPS).index("grassland") + 1
    cover = np.full((grid.height, grid.width), number)
    burned = (np.ones(cover.shape), np.zeros(cover.shape))
    shape = (days, cells.height, cells.width)
    daily = {"vpd_kpa": np.full(shape, 3.0), "temp_c": np.full(shape, 30.0)}
    daily |= {"wind_kmh": np.full(shape, 12.0), "rain_mm": np.full(shape, 2.0)}
    wind = np.zeros((days * 4, 3, cells.height, cells.width))
    wind[:, 0], wind[:, 2] = 10.0, 10.0  # 10 km/h to the east.
    return front_inputs.Layers(cover, burned, date(2022, 12, 1), daily, wind)


def test_the_ground_inputs_give_the_cover_on_the_front_and_ahead_of_it():
    centre = fronts.metres(np.array([-19.0]), np.array([-57.0]))
    look = fronts.make_look(centre + ROW, np.empty((0, 2)))
    reach = np.full((1, 8), 400.0)
    inputs = front_inputs.ground_inputs(look, layers_of(40), centre, reach)
    assert (inputs["on_grassland"][0], inputs["on_forest"][0]) == (1.0, 0.0)
    assert (inputs["burned_last_year"][0], inputs["burned_before"][0]) == (1.0, 0.0)
    assert inputs["ahead_grassland_s"].tolist() == [[1.0] * 8]
    assert inputs["ahead_burned_last_year_s"].tolist() == [[1.0] * 8]


def test_the_weather_before_a_look_and_the_wind_to_each_sector():
    centre = fronts.metres(np.array([-19.0]), np.array([-57.0]))
    start = datetime(2023, 1, 5, 5, 0, tzinfo=UTC).timestamp()
    inputs = front_inputs.weather_inputs(layers_of(40), centre, start, start + 600)
    assert (inputs["past_vpd"][0], inputs["past_temp"][0], inputs["past_wind"][0]) == (
        3.0,
        30.0,
        12.0,
    )
    assert inputs["rain_7"][0] == pytest.approx(np.log1p(14.0))
    assert inputs["rain_30"][0] == pytest.approx(np.log1p(60.0))
    toward = inputs["past_wind_toward_s"][0]
    assert (toward[EAST], toward[WEST], toward[NORTH]) == pytest.approx((10.0, -10.0, 0.0))
    assert inputs["wind_direction_deg"][0] == pytest.approx(90.0)


def test_a_look_after_the_last_day_of_the_weather_has_no_weather():
    centre = fronts.metres(np.array([-19.0]), np.array([-57.0]))
    start = datetime(2023, 3, 1, 5, 0, tzinfo=UTC).timestamp()
    inputs = front_inputs.weather_inputs(layers_of(40), centre, start, start + 600)
    assert np.isnan(inputs["past_vpd"][0]) and np.isnan(inputs["past_wind_toward_s"]).all()
