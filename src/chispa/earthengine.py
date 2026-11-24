"""Read a grid of pixels from Google Earth Engine, and send a request again after a failure.

Some sources are images in Earth Engine. Each of them needs the same request:
the values of one image on one of our grids. Earth Engine limits the size of one request,
thus we read the grid in tiles.
"""

import io
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

import ee
import numpy as np

from chispa import config
from chispa.grid import Grid

TILE_PX = 512  # The side of one request in pixels.

Box = tuple[float, float, float, float]  # south, west, north, east
Period = tuple[datetime, datetime]


def region_of(box: Box) -> ee.Geometry:
    """Return a box as a rectangle of Earth Engine."""
    south, west, north, east = box
    return ee.Geometry.Rectangle([west, south, east, north])  # Earth Engine uses lon, lat.


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


def again(request: Callable[[], Any]) -> Any:
    """Send a request to Earth Engine. A request that fails is sent again after a pause.

    Earth Engine refuses a request when too many run at one time. The last failure stops the run.
    """
    for attempt in range(1, config.EARTHENGINE_TRIES + 1):
        try:
            return request()
        except ee.EEException:
            if attempt == config.EARTHENGINE_TRIES:
                raise
            time.sleep(10 * attempt)
    return None
