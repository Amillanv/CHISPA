"""Sentinel-2 images through Google Earth Engine, for the image check of events.

Sentinel-2 has pixels of 10 m to 20 m and a new image each 5 days.
A burn shows as a dark red area in an image of the bands B12, B8 and B4.
This module finds an image near a date and saves a small picture of one box.
It also measures the burned area in a box from the change of the burn ratio (dNBR).
"""

import math
from datetime import UTC, datetime
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
        line = ee.Image().byte().paint(ee.FeatureCollection([ee.Feature(_region(shape))]), 1, 1)
        picture = picture.blend(line.visualize(palette=colour))
    url = picture.getThumbURL({"region": _region(box), "dimensions": pixels, "format": "png"})
    answer = requests.get(url, timeout=300)
    answer.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(answer.content)


# The scene classes of a pixel that we do not use: no data, defect, cloud shadow, water, cloud
# and cirrus. Water that dries decreases the burn ratio as a burn does.
NOT_CLEAR = (0, 1, 3, 6, 8, 9, 10)
# The scene classes that hide the ground from a person: no data, defect, cloud and cirrus.
# Cloud shadow is not in this list: the scene classes can give a new burn that class.
CLOUD = (0, 1, 8, 9, 10)
SCALE_M = 20  # The pixel size of the bands B8A and B12.

Period = tuple[datetime, datetime]


def _clear(image: ee.Image) -> ee.Image:
    """Return an image with only its clear pixels: no cloud, no shadow and no water."""
    scene = image.select("SCL")
    return image.updateMask(ee.Image(1).subtract(scene.remap(NOT_CLEAR, [1] * len(NOT_CLEAR), 0)))


def _view(images: ee.ImageCollection, period: Period, newest: bool) -> ee.Image | None:
    """Return one image of a period: each pixel from its newest or its oldest clear view."""
    chosen = images.filterDate(period[0].isoformat(), period[1].isoformat())
    if chosen.size().getInfo() == 0:
        return None
    # A mosaic shows the last image of the collection on top.
    return chosen.map(_clear).sort("system:time_start", newest).mosaic()


def _decrease(first: ee.Image, last: ee.Image, pair: list[str], sums: dict) -> tuple:
    """Return how much a ratio of two bands decreased from the view before to the view after,
    minus the median decrease of the box, and that median.

    The ratio is (a - b) / (a + b). With B8A and B12 it is the burn ratio NBR: healthy plants
    give a high value, and a burn gives a low value. With B11 and B12 it is NBR2, from the two
    short-wave bands. The median is the background: plants that dry change all of the box.
    """
    raw = first.normalizedDifference(pair).subtract(last.normalizedDifference(pair))
    raw = raw.rename("change")
    median = raw.reduceRegion(**{**sums, "reducer": ee.Reducer.median()}).get("change")
    background = ee.Number(ee.Algorithms.If(median, median, 0))  # A box with no clear pixel.
    return raw.subtract(ee.Image.constant(background)), background


def _step_areas(change: ee.Image, short: ee.Image, dark: ee.Image, hectares: ee.Image) -> dict:
    """Return one band of burned hectares for each step and each dark limit, by its key.

    The key of a dNBR step alone is its value as text, for example "0.3". With a dark limit,
    the pixel must also have a near infrared reflectance after the event of that limit or less:
    the key is "0.3/0.2". A burn is dark. Bare ground and a dry field are bright.
    A step of the short-wave ratio always has a dark limit: its key is "nbr2:0.1/0.2".
    """
    patch_px = round(config.BURN_PATCH_HA * 10_000 / SCALE_M**2)

    def area(chosen: ee.Image) -> ee.Image:
        in_patch = chosen.selfMask().connectedPixelCount(patch_px + 1, True).gte(patch_px)
        return hectares.updateMask(in_patch)

    bands = {}
    for step in config.BURN_DNBR_STEPS:
        bands[str(step)] = area(change.gte(step))
        for limit in config.BURN_DARK_STEPS:
            bands[f"{step}/{limit}"] = area(change.gte(step).And(dark.lte(limit)))
    for step in config.BURN_NBR2_STEPS:
        for limit in config.BURN_DARK_STEPS:
            bands[f"nbr2:{step}/{limit}"] = area(short.gte(step).And(dark.lte(limit)))
    return bands


def burned_areas(box: Box, before: Period, after: Period) -> dict[str, float]:
    """Return the clear share of the box, its background, and the burned hectares for each key.

    dNBR is the burn ratio before minus the burn ratio after, minus the background of the box.
    A pixel counts as burned at a step if that value is the step or more, and it is in a patch
    of the minimum size in `config.py`. `_step_areas` gives the keys.
    """
    images = ee.ImageCollection(ASSET).filterBounds(_region(box))
    first = _view(images, before, newest=True)
    last = _view(images, after, newest=False)
    if first is None or last is None:
        return {"clear_share": 0.0}
    # The pixel limit counts each band. A box of 100 km with all the bands needs more than 1e9.
    sums = {"reducer": None, "geometry": _region(box), "scale": SCALE_M, "maxPixels": 1e10}
    change, background = _decrease(first, last, ["B8A", "B12"], sums)
    short, _ = _decrease(first, last, ["B11", "B12"], sums)
    hectares = ee.Image.pixelArea().divide(10_000)
    steps = _step_areas(change, short, last.select("B8A").divide(10_000), hectares)
    names = {key: f"area_{number}" for number, key in enumerate(steps)}  # No point in a name.
    bands = [hectares.rename("box"), hectares.updateMask(change.mask()).rename("clear")]
    bands += [band.rename(names[key]) for key, band in steps.items()]
    areas = ee.Image.cat(bands).reduceRegion(**{**sums, "reducer": ee.Reducer.sum()})
    found = areas.set("background", background).getInfo()
    clear_share = round(found["clear"] / found["box"], 4)
    burned = {key: round(found[name], 2) for key, name in names.items()}
    return {"clear_share": clear_share, "background": round(found["background"], 4), **burned}


def cloud_free_views(box: Box, start: datetime, end: datetime) -> list[tuple[str, datetime, float]]:
    """Return each image of a period that covers the box: name, time and cloud-free share.

    The share is for the pixels of the box, not for the full image tile. The oldest image is first.
    """
    region = _region(box)

    def with_share(image: ee.Image) -> ee.Image:
        # A pixel with no value in the image counts as hidden.
        seen = image.select("SCL").remap(CLOUD, [0] * len(CLOUD), 1).unmask(0)
        share = seen.reduceRegion(ee.Reducer.mean(), region, SCALE_M).get("remapped")
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


def burned_by_day(box: Box, before: Period, start: datetime, ends: dict, rule: tuple) -> dict:
    """Return the burn curve of a box: for each day, the number of images, the share of the box
    with a clear view, and the burned hectares.

    `ends` gives the end time of each day. `rule` is the dNBR step and the dark limit.
    The answer of a day uses the images from `start`, after the event, to the end of that day.
    Each pixel has one view: its oldest clear view in those images. Thus a later image adds
    pixels, and it does not look at a pixel a second time. A pixel is burned if its burn ratio
    decreased from the view before the event by the step or more, minus the background, and
    if its near infrared reflectance is the dark limit or less, in a patch of the minimum size.
    A day that ends before `start` has no image. With no view before the event: no value.
    """
    region = _region(box)
    images = ee.ImageCollection(ASSET).filterBounds(region)
    view = _view(images, before, newest=True)
    days = [day for day, end in ends.items() if end > start]
    if view is None or not days:
        return {}
    ratio = view.normalizedDifference(["B8A", "B12"])
    sums = {"geometry": region, "scale": SCALE_M, "maxPixels": 1e10}
    hectares = ee.Image.pixelArea().divide(10_000)
    patch_px = round(config.BURN_PATCH_HA * 10_000 / SCALE_M**2)
    # A period with no image gives an image with no clear pixel, not an error.
    hidden = ee.Image.constant([0, 0]).rename(["B8A", "B12"]).updateMask(0).toUint16()
    bands, counts = [hectares.rename("box")], []
    for day in days:
        to_day = images.filterDate(start.isoformat(), ends[day].isoformat())
        counts.append(to_day.size())
        # The oldest image is last in the sequence, thus it is on top.
        oldest = to_day.map(_clear).select(["B8A", "B12"]).sort("system:time_start", False)
        after = ee.ImageCollection([hidden]).merge(oldest).mosaic()
        raw = ratio.subtract(after.normalizedDifference(["B8A", "B12"])).rename("change")
        median = raw.reduceRegion(reducer=ee.Reducer.median(), **sums).get("change")
        change = raw.subtract(ee.Image.constant(ee.Number(ee.Algorithms.If(median, median, 0))))
        burned = change.gte(rule[0]).And(after.select("B8A").divide(10_000).lte(rule[1]))
        in_patch = burned.selfMask().connectedPixelCount(patch_px + 1, True).gte(patch_px)
        bands.append(hectares.updateMask(in_patch).rename(f"burned_{day}"))
        bands.append(hectares.updateMask(change.mask()).rename(f"clear_{day}"))
    areas = ee.Image.cat(bands).reduceRegion(reducer=ee.Reducer.sum(), **sums)
    found = ee.Dictionary({"areas": areas, "views": ee.List(counts)}).getInfo()
    areas = found["areas"]
    return {
        day: (
            views,
            round(areas[f"clear_{day}"] / areas["box"], 4),
            round(areas[f"burned_{day}"], 2),
        )
        for day, views in zip(days, found["views"], strict=True)
    }
