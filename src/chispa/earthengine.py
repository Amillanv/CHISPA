"""Read a grid of pixels from Google Earth Engine.

Some sources are images in Earth Engine. Each of them needs the same request:
the values of one image on one of our grids. Earth Engine limits the size of one request,
thus we read the grid in tiles.
"""

import io

import ee
import numpy as np

from chispa.grid import Grid

TILE_PX = 512  # The side of one request in pixels.


def read_grid(image: ee.Image, grid: Grid) -> np.ndarray:
    """Return the first band of an image as an array on the grid. Row 0 is the north edge."""
    tiles = []
    for row in range(0, grid.height, TILE_PX):
        strip = []
        for col in range(0, grid.width, TILE_PX):
            size = (min(TILE_PX, grid.width - col), min(TILE_PX, grid.height - row))
            tile = read_window(image, grid, (row, col), size)
            strip.append(tile[tile.dtype.names[0]])
        tiles.append(np.concatenate(strip, axis=1))
    return np.concatenate(tiles, axis=0)


def read_window(image: ee.Image, grid: Grid, start: tuple[int, int], size: tuple[int, int]):
    """Return a part of the grid in one request, as an array with one field for each band.

    `start` is the row and the column of the north-west pixel. `size` is the width and the height.
    """
    row, col = start
    request = {
        "expression": image,
        "fileFormat": "NPY",
        "grid": {
            "dimensions": {"width": size[0], "height": size[1]},
            "affineTransform": {
                "scaleX": grid.pixel_deg,
                "shearX": 0,
                "translateX": grid.west + col * grid.pixel_deg,
                "shearY": 0,
                "scaleY": -grid.pixel_deg,
                "translateY": grid.north - row * grid.pixel_deg,
            },
            "crsCode": "EPSG:4326",
        },
    }
    return np.load(io.BytesIO(ee.data.computePixels(request)))
