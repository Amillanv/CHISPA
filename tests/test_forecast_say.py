"""Tests of the counts of what the forecast says, with cases small enough for paper."""

import numpy as np
import pytest

from chispa.evaluation import forecast_say


@pytest.fixture(autouse=True)
def fixed_values(monkeypatch):
    monkeypatch.setattr("chispa.config.FORECAST_BANDS", (0.2, 0.5))
    monkeypatch.setattr("chispa.config.FORECAST_TOP_SECTORS", (1, 2))
    monkeypatch.setattr("chispa.config.FRONT_SECTORS", 8)
    monkeypatch.setattr("chispa.config.FRONT_DIRECTION_PIXELS", 3)
    monkeypatch.setattr("chispa.config.ADVANCE_SAME_DEG", 45.0)


def test_a_band_counts_its_rows_and_how_many_had_the_answer_yes():
    chance = np.array([0.1, 0.2, 0.4, 0.5, 1.0])
    label = np.array([0.0, 1.0, 0.0, 1.0, 1.0])
    low, middle, high = forecast_say.chance_rows(("new_ground", 12), chance, label)
    # 0.1 is in the first band. 0.2 and 0.4 are in the second. 0.5 and 1.0 are in the last.
    assert (low["rows"], low["came"], low["came_share"]) == (1, 0, 0.0)
    assert (middle["rows"], middle["came"], middle["chance_mean"]) == (2, 1, 0.3)
    assert (high["rows"], high["came"], high["came_share"]) == (2, 2, 1.0)
    assert (high["chance_from"], high["chance_to"]) == (0.5, 1.0)


def test_a_band_with_no_row_has_no_share():
    rows = forecast_say.chance_rows(("new_ground", 12), np.array([0.9]), np.array([1.0]))
    assert rows[0]["rows"] == 0 and rows[0]["came_share"] is None and rows[0]["chance_mean"] is None


def test_the_most_likely_sectors_count_the_new_pixels_of_a_front():
    # Front 1: 4 new pixels to the north and 2 to the east. The forecast says east, then north.
    # Front 2: 3 new pixels to the south. The forecast says west, then north.
    # Front 3 has 2 new pixels: it is below the minimum for a direction. Front 4 has no row.
    pixels = np.zeros((4, 8), dtype=int)
    pixels[0, 0], pixels[0, 2], pixels[1, 4], pixels[2, 0], pixels[3, 0] = 4, 2, 3, 2, 9
    chance = np.zeros((3, 8))
    chance[0, 2], chance[0, 0] = 0.6, 0.5
    chance[1, 6], chance[1, 0] = 0.6, 0.5
    use = np.array([True, True, True, False])
    row = forecast_say.sector_row({"sectors_12": pixels}, 12, use, chance.ravel())
    assert (row["fronts"], row["new_pixels"]) == (2, 9)
    assert (row["top_1_fronts"], row["top_1_pixels"]) == (1, 2)
    assert (row["top_2_fronts"], row["top_2_pixels"]) == (1, 6)
    # 3 of the 16 sectors of the two fronts got a new pixel.
    assert row["sector_by_chance"] == round(3 / 16, 4)


def test_the_first_look_of_a_fire_and_the_examined_places_have_their_scores_apart():
    # Fronts 1 and 2 are a first look. Front 1 gets 3 new pixels to the east, and the forecast
    # says east. Front 3 gets 4 new pixels to the north, and the forecast says south.
    # GOES examined the place of the fronts 1, 2 and 4, and not that of the front 3.
    rows = {
        "inputs": {"first_look": np.array([True, True, False, False])},
        "answers": {
            "new_12": np.array([3, 0, 4, 0]),
            "direction_deg_12": np.array([90.0, np.nan, 0.0, np.nan]),
            "examined_12": np.array([True, True, False, True]),
        },
    }
    sector = np.zeros((4, 8))
    sector[0, 2], sector[2, 4] = 0.5, 0.5
    trees = {"new_ground": np.array([0.8, 0.2, 0.3, 0.6]), "sector": sector.ravel()}
    found = forecast_say.group_rows(rows, 12, np.ones(4, dtype=bool), trees)
    first, other = found["forecast_first_look"]
    assert (first["fronts"], first["rows"], first["new_ground"]) == ("first look", 2, 1)
    assert (first["auc_trees"], first["fronts_with_direction"], first["trees_in_45"]) == (1.0, 1, 1)
    assert (other["rows"], other["new_ground"], other["auc_trees"]) == (2, 1, 0.0)
    assert (other["fronts_with_direction"], other["trees_in_45"]) == (1, 0)
    # The stated chances of the first two fronts expect 0.8 + 0.2 = 1 front with new ground.
    assert first["chance_sum"] == 1.0
    seen, dark = found["forecast_examined"]
    assert (seen["fronts"], seen["rows"], seen["new_ground"], seen["chance_sum"]) == (
        "examined",
        3,
        1,
        1.6,
    )
    assert (dark["fronts"], dark["rows"], dark["new_ground"]) == ("not examined", 1, 1)
