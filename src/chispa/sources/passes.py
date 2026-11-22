"""The pass times of the VIIRS satellites, from the NASA Common Metadata Repository (CMR).

A detection says where a satellite saw heat. It does not say when a satellite looked and saw
no heat. CMR lists each granule of the VIIRS fire product: a part of one pass, with its time
and the outline of the ground that it covers. Thus a pass with no detection becomes visible.
A granule does not say if cloud hid a place.
"""

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import requests

from chispa import config

API = "https://cmr.earthdata.nasa.gov/search/granules.json"
PRODUCTS = {"VNP14IMG": "SNPP", "VJ114IMG": "NOAA20", "VJ214IMG": "NOAA21"}
PAGE = 2000  # One year of one product over the Pantanal box has approximately 1400 granules.


def download_year(year: int, raw_dir: Path) -> list[Path]:
    """Save the granule list of each VIIRS product for one year and return the paths."""
    west, south, east, north = config.PANTANAL_BOX
    paths = []
    for product in PRODUCTS:
        path = raw_dir / "passes" / str(year) / f"{product}.json"
        if not path.exists():
            answer = requests.get(
                API,
                params={
                    "short_name": product,
                    "bounding_box": f"{west},{south},{east},{north}",
                    "temporal": f"{year}-01-01T00:00:00Z,{year + 1}-01-01T00:00:00Z",
                    "page_size": PAGE,
                },
                timeout=180,
            )
            answer.raise_for_status()
            if int(answer.headers["CMR-Hits"]) > PAGE:
                raise RuntimeError(f"{product} has more than {PAGE} granules. Get them in parts.")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(answer.text)
        paths.append(path)
    return paths


def parse_file(path: Path) -> list[tuple[str, float, np.ndarray]]:
    """Return (platform, start time in seconds, outline) for each granule of one file.

    The outline has one row for each corner: latitude, longitude.
    """
    platform = PRODUCTS[path.stem]
    granules = []
    for entry in json.loads(path.read_text())["feed"]["entry"]:
        start = datetime.fromisoformat(entry["time_start"].replace("Z", "+00:00")).timestamp()
        corners = np.array(entry["polygons"][0][0].split(), dtype=float).reshape(-1, 2)
        granules.append((platform, start, corners))
    return granules


def read_year(year: int, raw_dir: Path) -> list[tuple[str, float, np.ndarray]]:
    """Return the granules of all VIIRS products for one year, in time sequence."""
    paths = sorted((raw_dir / "passes" / str(year)).glob("*.json"))
    if len(paths) != len(PRODUCTS):
        raise RuntimeError(f"The pass files of {year} are absent. Run `chispa fetch passes`.")
    return sorted((granule for path in paths for granule in parse_file(path)), key=lambda g: g[1])


def covers(outline: np.ndarray, lat: float, lon: float) -> bool:
    """Return True if the outline of a granule holds the position.

    A line from the position to the east crosses the edge of the outline an odd number of times.
    """
    lats, lons = outline[:, 0], outline[:, 1]
    next_lats, next_lons = np.roll(lats, -1), np.roll(lons, -1)
    crosses = (lats > lat) != (next_lats > lat)
    with np.errstate(divide="ignore", invalid="ignore"):
        at_lon = lons + (lat - lats) / (next_lats - lats) * (next_lons - lons)
    return bool((crosses & (at_lon > lon)).sum() % 2)
