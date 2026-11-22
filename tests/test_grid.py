"""Tests of the grids."""

from chispa.grid import layer_grid, pantanal_grid


def test_layer_grid_covers_each_pixel_of_the_scar_grid(monkeypatch):
    monkeypatch.setattr("chispa.config.LAYER_CELLS", 10)
    scars, layers = pantanal_grid(), layer_grid()
    assert layers.width * 10 >= scars.width > (layers.width - 1) * 10
    assert layers.height * 10 >= scars.height > (layers.height - 1) * 10
    # The centre of the last scar pixel is in the last cell of the layer grid.
    rows, cols = layers.rows_cols(scars.lats()[-1:], scars.lons()[-1:])
    assert (rows[0], cols[0]) == (layers.height - 1, layers.width - 1)
