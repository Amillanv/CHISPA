"""Tests of the run for the fronts in Brazil outside the biome, with cases for paper."""

import numpy as np

from chispa.evaluation import forecast_outside
from chispa.grid import Grid


def test_a_pixel_is_in_brazil_if_its_layer_cell_has_a_land_cover_class(monkeypatch, tmp_path):
    # A grid of 3 rows and 5 columns of pixels. A layer cell is a square of 2 pixels.
    monkeypatch.setattr(forecast_outside, "pantanal_grid", lambda: Grid(0.0, 0.0, 1.0, 5, 3))
    monkeypatch.setattr("chispa.config.LAYER_CELLS", 2)
    cover = np.array([[3, 0, 0], [0, 12, 0]], dtype=np.uint8)
    monkeypatch.setattr(forecast_outside.landcover, "read_year", lambda year, raw_dir: cover)
    found = forecast_outside.brazil(tmp_path)
    # The last layer column and the last layer row go past the grid: the answer has its size.
    assert found.astype(int).tolist() == [[1, 1, 0, 0, 0], [1, 1, 0, 0, 0], [0, 0, 1, 1, 0]]


def test_the_centre_of_a_front_says_if_it_is_in_the_biome(monkeypatch, tmp_path):
    # 2 rows and 3 columns of 1 degree. The row centres are -15.5 and -16.5.
    monkeypatch.setattr(forecast_outside, "pantanal_grid", lambda: Grid(-60.0, -15.0, 1.0, 3, 2))
    in_biome = np.array([[False, True, False], [False, False, False]])
    with_class = np.array([[False, False, True], [False, False, True]])
    monkeypatch.setattr(forecast_outside.border, "read_rings", lambda path: [])
    monkeypatch.setattr(forecast_outside.border, "rasterize", lambda rings, grid: in_biome)
    monkeypatch.setattr(forecast_outside, "brazil", lambda raw_dir: with_class)
    masks = []

    def year_rows(year, store_path, raw_dir, counted):
        masks.append(counted)
        # One front in the biome, and two fronts in the column with a class.
        answers = {"lat": np.array([-15.5, -15.5, -16.5]), "lon": np.array([-58.5, -57.5, -57.5])}
        return {"answers": answers | {"pixels": np.array([3, 4, 5])}, "inputs": {"x": np.arange(3)}}

    monkeypatch.setattr(forecast_outside.forecast, "year_rows", year_rows)
    inside, outside = forecast_outside.year_parts(tmp_path, tmp_path, (2023,))
    # A front counts in the biome, also with no class, or in a cell with a class.
    assert masks[0].astype(int).tolist() == [[0, 1, 1], [0, 0, 1]]
    assert inside[2023]["answers"]["pixels"].tolist() == [3]
    assert outside[2023]["answers"]["pixels"].tolist() == [4, 5]
    assert outside[2023]["inputs"]["x"].tolist() == [1, 2]


def test_the_trees_come_from_the_biome_and_the_score_from_the_fronts_outside(monkeypatch, tmp_path):
    monkeypatch.setattr("chispa.config.FRONT_YEARS", (2019, 2020))
    monkeypatch.setattr("chispa.config.FRONT_TEST_YEARS", (2021,))

    def year_parts(store_path, raw_dir, years):
        return {year: f"biome {year}" for year in years}, {
            year: f"outside {year}" for year in years
        }

    def year_tables(rows, cases, year, training):
        # The row says which fronts get the score, and which fronts the trees learn from.
        row = {"scored": cases[year], "rows": rows[year], "trees": [cases[one] for one in training]}
        return {"forecast": [row], "forecast_direction": [], "forecast_inputs": ["not kept"]}

    monkeypatch.setattr(forecast_outside, "year_parts", year_parts)
    monkeypatch.setattr(forecast_outside.forecast_run, "year_cases", lambda rows: dict(rows))
    monkeypatch.setattr(forecast_outside.forecast_run, "year_tables", year_tables)
    tables = forecast_outside.outside_tables(tmp_path, tmp_path, test_run=False)
    assert sorted(tables) == [2019, 2020]
    assert set(tables[2019]) == {"forecast_outside", "forecast_direction_outside"}
    (row,) = tables[2019]["forecast_outside"]
    assert row == {"scored": "outside 2019", "rows": "outside 2019", "trees": ["biome 2020"]}
    # A test year gets the trees of the two development years, from the biome only.
    tables = forecast_outside.outside_tables(tmp_path, tmp_path, test_run=True)
    (row,) = tables[2021]["forecast_outside"]
    assert (row["scored"], row["trees"]) == ("outside 2021", ["biome 2019", "biome 2020"])
