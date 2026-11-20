"""The border of the Pantanal biome from IBGE, the Brazilian statistics institute.

We request data for a box, but we report results for the biome.
This module gets the official border and converts it to a grid mask.
"""

import json
from pathlib import Path

import numpy as np
import requests

from chispa.grid import Grid

# The layer has the six biomes of Brazil at the scale 1:250 000. The Pantanal has the code 6.
URL = (
    "https://geoservicos.ibge.gov.br/geoserver/ows?service=WFS&version=1.0.0"
    "&request=GetFeature&typeName=CREN:lm_bioma_250&outputFormat=application/json"
    "&CQL_FILTER=cd_bioma=6"
)


def download(raw_dir: Path) -> Path:
    """Save the border as one GeoJSON file and return the path."""
    path = raw_dir / "border" / "pantanal.geojson"
    if path.exists():
        return path
    answer = requests.get(URL, timeout=300)
    answer.raise_for_status()
    names = [feature["properties"]["bioma"] for feature in answer.json()["features"]]
    if names != ["Pantanal"]:
        raise RuntimeError(f"IBGE gave the features {names}, not only the Pantanal.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(answer.content)
    return path


def read_rings(path: Path) -> list[np.ndarray]:
    """Return each ring of the border as an array of (lon, lat) points.

    The file uses the datum SIRGAS 2000. It is less than one metre from WGS84.
    """
    geometry = json.loads(path.read_text())["features"][0]["geometry"]
    polygons = (
        geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
    )
    return [np.array(ring)[:, :2] for polygon in polygons for ring in polygon]


def rasterize(rings: list[np.ndarray], grid: Grid) -> np.ndarray:
    """Return a grid that is True where the centre of a pixel is in the border.

    For each row we find where the border crosses the row. The pixels between
    the first and the second crossing are in, between the third and the fourth, and so on.
    A hole in a polygon adds two crossings, thus the hole stays out.
    """
    starts = np.concatenate([ring[:-1] for ring in rings])
    ends = np.concatenate([ring[1:] for ring in rings])
    x1, y1, x2, y2 = starts[:, 0], starts[:, 1], ends[:, 0], ends[:, 1]
    mask = np.zeros((grid.height, grid.width), dtype=bool)
    for row, lat in enumerate(grid.lats()):
        crosses = (y1 <= lat) != (y2 <= lat)
        if not crosses.any():
            continue
        lon = x1[crosses] + (lat - y1[crosses]) * (x2[crosses] - x1[crosses]) / (
            y2[crosses] - y1[crosses]
        )
        # The first column with its centre east of a crossing.
        cols = np.ceil((np.sort(lon) - grid.west) / grid.pixel_deg - 0.5).astype(int)
        cols = np.clip(cols, 0, grid.width)
        for first, after_last in zip(cols[0::2], cols[1::2], strict=True):
            mask[row, first:after_last] = True
    return mask
