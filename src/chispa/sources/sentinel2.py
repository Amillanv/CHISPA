"""Sentinel-2 images through Google Earth Engine, for the image check of events.

Sentinel-2 has pixels of 10 m to 20 m and a new image each 5 days.
A burn shows as a dark red area in an image of the bands B12, B8 and B4.
This module finds an image near a date and saves a small picture of one box.
It also measures the burned area in a box from the change of the burn ratio (dNBR).
"""

from datetime import datetime
from pathlib import Path

import ee
import requests

from chispa import config

ASSET = "COPERNICUS/S2_SR_HARMONIZED"
# Short-wave infrared, near infrared and red. Healthy plants are green. A new burn is dark red.
PICTURE = {"bands": ["B12", "B8", "B4"], "min": 0, "max": 4000}

Box = tuple[float, float, float, float]  # south, west, north, east


def _region(box: Box) -> ee.Geometry:
    south, west, north, east = box
    return ee.Geometry.Rectangle([west, south, east, north])  # Earth Engine uses lon, lat.


def find_image(box: Box, start: datetime, end: datetime, newest: bool) -> tuple[str, float] | None:
    """Return the name and the cloud percentage of one image that covers the box, or None.

    The image is between the two times and has less cloud than the limit in `config.py`.
    `newest` selects the last such image. If not, the first image is selected.
    The cloud percentage is for the full image tile, not for the box.
    """
    images = (
        ee.ImageCollection(ASSET)
        .filterBounds(_region(box))  # Quick. It keeps each image that touches the box.
        .filterDate(start.isoformat(), end.isoformat())
        .filter(ee.Filter.contains(".geo", _region(box)))  # The image must cover all of the box.
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", config.IMAGE_MAX_CLOUD))
        .sort("system:time_start", not newest)
    )
    found = images.first().getInfo()
    if found is None:
        return None
    return found["properties"]["system:index"], found["properties"]["CLOUDY_PIXEL_PERCENTAGE"]


def save_picture(name: str, box: Box, outline: Box, path: Path) -> None:
    """Save a picture of the box from one image, with the outline as a yellow line."""
    south, west, north, east = box
    side_m = max((north - south) * 110_574, (east - west) * 111_320)
    pixels = int(min(max(side_m / config.IMAGE_M_PER_PX, 256), config.IMAGE_MAX_PX))
    line = ee.Image().byte().paint(ee.FeatureCollection([ee.Feature(_region(outline))]), 1, 1)
    picture = (
        ee.Image(f"{ASSET}/{name}").visualize(**PICTURE).blend(line.visualize(palette="ffff00"))
    )
    url = picture.getThumbURL({"region": _region(box), "dimensions": pixels, "format": "png"})
    answer = requests.get(url, timeout=300)
    answer.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(answer.content)


# The scene classes of a pixel that we do not use: no data, defect, cloud shadow, water, cloud
# and cirrus. Water that dries decreases the burn ratio as a burn does.
NOT_CLEAR = (0, 1, 3, 6, 8, 9, 10)
SCALE_M = 20  # The pixel size of the bands B8A and B12.

Period = tuple[datetime, datetime]


def _burn_ratio(images: ee.ImageCollection, period: Period, newest: bool) -> ee.Image | None:
    """Return the burn ratio (NBR) of each pixel from its newest or its oldest clear view.

    NBR is (B8A - B12) / (B8A + B12). Healthy plants give a high value. A burn gives a low value.
    """
    chosen = images.filterDate(period[0].isoformat(), period[1].isoformat())
    if chosen.size().getInfo() == 0:
        return None

    def clear(image: ee.Image) -> ee.Image:
        scene = image.select("SCL")
        return image.updateMask(
            ee.Image(1).subtract(scene.remap(NOT_CLEAR, [1] * len(NOT_CLEAR), 0))
        )

    # A mosaic shows the last image of the collection on top.
    views = chosen.map(clear).sort("system:time_start", newest)
    return views.mosaic().normalizedDifference(["B8A", "B12"])


def burned_areas(box: Box, before: Period, after: Period) -> dict[str, float]:
    """Return the clear share of the box, its background, and the burned hectares for each step.

    dNBR is the burn ratio before minus the burn ratio after. The background is the median dNBR
    of the box: plants that dry in the season change all of the box, and a burn changes a part.
    A pixel counts as burned at a step if its dNBR minus the background is the step or more,
    and it is in a patch of the minimum size in `config.py`.
    The key of a step is its value as text, for example "0.1".
    """
    images = ee.ImageCollection(ASSET).filterBounds(_region(box))
    first = _burn_ratio(images, before, newest=True)
    last = _burn_ratio(images, after, newest=False)
    if first is None or last is None:
        return {"clear_share": 0.0}
    raw = first.subtract(last).rename("dnbr")
    sums = {"reducer": None, "geometry": _region(box), "scale": SCALE_M, "maxPixels": 1e9}
    median = raw.reduceRegion(**{**sums, "reducer": ee.Reducer.median()}).get("dnbr")
    background = ee.Number(ee.Algorithms.If(median, median, 0))  # A box with no clear pixel.
    change = raw.subtract(ee.Image.constant(background))
    hectares = ee.Image.pixelArea().divide(10_000)
    patch_px = round(config.BURN_PATCH_HA * 10_000 / SCALE_M**2)
    bands = [hectares.rename("box"), hectares.updateMask(change.mask()).rename("clear")]
    for number, step in enumerate(config.BURN_DNBR_STEPS):
        high = change.gte(step).selfMask()
        in_patch = high.connectedPixelCount(patch_px + 1, True).gte(patch_px)
        bands.append(hectares.updateMask(in_patch).rename(f"step_{number}"))  # No point in a name.
    areas = ee.Image.cat(bands).reduceRegion(**{**sums, "reducer": ee.Reducer.sum()})
    sums = areas.set("background", background).getInfo()
    areas = {
        str(step): round(sums[f"step_{number}"], 2)
        for number, step in enumerate(config.BURN_DNBR_STEPS)
    }
    clear_share = round(sums["clear"] / sums["box"], 4)
    return {"clear_share": clear_share, "background": round(sums["background"], 4), **areas}
