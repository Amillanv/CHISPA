"""A regular grid of pixels in latitude and longitude.

The burn scar maps and the biome mask are grids. One small class gives the position
of each pixel, thus all modules agree on where a pixel is.
"""

from dataclasses import dataclass

import numpy as np

from chispa import config


@dataclass(frozen=True)
class Grid:
    """A grid with square pixels. Row 0 is the north edge. Column 0 is the west edge."""

    west: float
    north: float
    pixel_deg: float
    width: int
    height: int

    def lats(self) -> np.ndarray:
        """Return the latitude of the centre of each row."""
        return self.north - (np.arange(self.height) + 0.5) * self.pixel_deg

    def lons(self) -> np.ndarray:
        """Return the longitude of the centre of each column."""
        return self.west + (np.arange(self.width) + 0.5) * self.pixel_deg

    def rows_cols(self, lat: np.ndarray, lon: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Return the row and the column of each position. A position can be off the grid."""
        rows = np.floor((self.north - lat) / self.pixel_deg).astype(int)
        cols = np.floor((lon - self.west) / self.pixel_deg).astype(int)
        return rows, cols


def layer_grid() -> Grid:
    """Return the grid of the severity layers: each cell is a square of scar pixels."""
    grid, cells = pantanal_grid(), config.LAYER_CELLS
    return Grid(
        grid.west, grid.north, grid.pixel_deg * cells, grid.width // cells, grid.height // cells
    )


def pantanal_grid() -> Grid:
    """Return the part of the MapBiomas grid that covers the Pantanal box."""
    west, south, east, north = config.PANTANAL_BOX
    origin_west, origin_north = config.SCAR_ORIGIN
    pixel = config.SCAR_PIXEL_DEG
    # We count whole pixels from the origin of the MapBiomas grid. Thus no pixel is resampled.
    first_col = int(np.floor((west - origin_west) / pixel))
    first_row = int(np.floor((origin_north - north) / pixel))
    return Grid(
        west=origin_west + first_col * pixel,
        north=origin_north - first_row * pixel,
        pixel_deg=pixel,
        width=int(np.ceil((east - origin_west) / pixel)) - first_col,
        height=int(np.ceil((origin_north - south) / pixel)) - first_row,
    )
