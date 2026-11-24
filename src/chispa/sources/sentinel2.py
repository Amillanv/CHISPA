"""Sentinel-2 images through Google Earth Engine, for the image check of events.

Sentinel-2 has pixels of 10 m to 20 m and a new image each 5 days.
A burn shows as a dark red area in an image of the bands B12, B8 and B4.
This module finds an image near a date, saves a small picture of one box, and gives the
cloud of a box in each image. `sentinel2_ground.py` measures the burned ground.
"""

import math
from datetime import UTC, datetime
from pathlib import Path

import ee
import requests

from chispa import config
from chispa.earthengine import Box, region_of

ASSET = config.SENTINEL2_ASSET
CLOUD = config.SENTINEL2_CLOUD
SCALE_M = config.SENTINEL2_SCALE_M

# Short-wave infrared, near infrared and red. Healthy plants are green. A new burn is dark red.
PICTURE = {"bands": ["B12", "B8", "B4"], "min": 0, "max": 4000}


def find_image(box: Box, start: datetime, end: datetime, newest: bool) -> tuple[str, float] | None:
    """Return the name and the cloud percentage of one image that covers the box, or None.

    The image is between the two times and has less cloud than the limit in `config.py`.
    `newest` selects the last such image. If not, the first image is selected.
    The cloud percentage is for the full image tile, not for the box.
    """
    images = (
        ee.ImageCollection(ASSET)
        .filterBounds(region_of(box))  # Quick. It keeps each image that touches the box.
        .filterDate(start.isoformat(), end.isoformat())
        .filter(ee.Filter.contains(".geo", region_of(box)))  # The image must cover all of the box.
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", config.IMAGE_MAX_CLOUD))
        .sort("system:time_start", not newest)
    )
    found = images.first().getInfo()
    if found is None:
        return None
    return found["properties"]["system:index"], found["properties"]["CLOUDY_PIXEL_PERCENTAGE"]


def scale_square(box: Box) -> Box:
    """Return a square with the minimum burned area of the rule, in the south-west corner of a box.

    A person uses it as a scale: a burn that is smaller than the square is a small burn.
    """
    south, west, north, east = box
    side_m = (config.BURN_HA_MIN * 10_000) ** 0.5
    d_lat = side_m / 110_574
    d_lon = side_m / (111_320 * math.cos(math.radians(south)))
    low, left = south + (north - south) * 0.02, west + (east - west) * 0.02
    return low, left, low + d_lat, left + d_lon


def save_picture(name: str, box: Box, outline: Box, path: Path) -> None:
    """Save a picture of the box from one image: the outline in yellow, the scale in white."""
    south, west, north, east = box
    side_m = max((north - south) * 110_574, (east - west) * 111_320)
    pixels = int(min(max(side_m / config.IMAGE_M_PER_PX, 256), config.IMAGE_MAX_PX))
    picture = ee.Image(f"{ASSET}/{name}").visualize(**PICTURE)
    for shape, colour in ((outline, "ffff00"), (scale_square(box), "ffffff")):
        line = ee.Image().byte().paint(ee.FeatureCollection([ee.Feature(region_of(shape))]), 1, 1)
        picture = picture.blend(line.visualize(palette=colour))
    url = picture.getThumbURL({"region": region_of(box), "dimensions": pixels, "format": "png"})
    answer = requests.get(url, timeout=300)
    answer.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(answer.content)


def cloud_free_views(box: Box, start: datetime, end: datetime) -> list[tuple[str, datetime, float]]:
    """Return each image of a period that covers the box: name, time and cloud-free share.

    The share is for the pixels of the box, not for the full image tile. The oldest image is first.
    """
    region = region_of(box)

    def with_share(image: ee.Image) -> ee.Image:
        # A pixel with no value in the image counts as hidden.
        seen = image.select("SCL").remap(CLOUD, [0] * len(CLOUD), 1).unmask(0)
        # The box of a very large event has more pixels than the first limit of a request.
        share = seen.reduceRegion(ee.Reducer.mean(), region, SCALE_M, maxPixels=1e10).get(
            "remapped"
        )
        return image.set("cloud_free", share)

    images = (
        ee.ImageCollection(ASSET)
        .filterBounds(region)
        .filterDate(start.isoformat(), end.isoformat())
        .filter(ee.Filter.contains(".geo", region))  # The image must cover all of the box.
        .map(with_share)
        .sort("system:time_start")
    )
    names = ("system:index", "system:time_start", "cloud_free")
    found = ee.Dictionary({name: images.aggregate_array(name) for name in names}).getInfo()
    times = [datetime.fromtimestamp(ms / 1000, UTC) for ms in found["system:time_start"]]
    return list(zip(found["system:index"], times, found["cloud_free"], strict=True))
