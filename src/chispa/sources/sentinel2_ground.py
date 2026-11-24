"""The burned ground of a box from Sentinel-2: the change of the burn ratio between two views.

Sentinel-2 has a short-wave band and a near infrared band. A burn decreases their ratio (NBR),
and it leaves the ground dark. This module measures the burned hectares of a box by rules on
those bands: for the burn check, for the candidates, for the burn curve and for the check
of an advance. `sentinel2.py` has the images, the pictures and the cloud of a box.
"""

from datetime import datetime, timedelta

import ee

from chispa import config
from chispa.earthengine import Box, Period, region_of

ASSET = config.SENTINEL2_ASSET
NOT_CLEAR = config.SENTINEL2_NOT_CLEAR
SCALE_M = config.SENTINEL2_SCALE_M


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
    images = ee.ImageCollection(ASSET).filterBounds(region_of(box))
    first = _view(images, before, newest=True)
    last = _view(images, after, newest=False)
    if first is None or last is None:
        return {"clear_share": 0.0}
    # The pixel limit counts each band. A box of 100 km with all the bands needs more than 1e9.
    sums = {"reducer": None, "geometry": region_of(box), "scale": SCALE_M, "maxPixels": 1e10}
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


def _one_look(ratio: ee.Image, images: ee.ImageCollection, period: Period, key: tuple) -> tuple:
    """Return two images for a period after an event: the pixels that the rule calls burned,
    and the pixels with a clear view.

    Each pixel has one view: its oldest clear view of the period. `key` is the rule (the dNBR
    step and the dark limit) and the sums of the box, for the background.
    """
    rule, sums = key
    patch_px = round(config.BURN_PATCH_HA * 10_000 / SCALE_M**2)
    # A period with no image gives an image with no clear pixel, not an error.
    hidden = ee.Image.constant([0, 0]).rename(["B8A", "B12"]).updateMask(0).toUint16()
    to_end = images.filterDate(period[0].isoformat(), period[1].isoformat())
    # The oldest image is last in the sequence, thus it is on top.
    oldest = to_end.map(_clear).select(["B8A", "B12"]).sort("system:time_start", False)
    after = ee.ImageCollection([hidden]).merge(oldest).mosaic()
    raw = ratio.subtract(after.normalizedDifference(["B8A", "B12"])).rename("change")
    median = raw.reduceRegion(reducer=ee.Reducer.median(), **sums).get("change")
    change = raw.subtract(ee.Image.constant(ee.Number(ee.Algorithms.If(median, median, 0))))
    burned = change.gte(rule[0]).And(after.select("B8A").divide(10_000).lte(rule[1]))
    in_patch = burned.selfMask().connectedPixelCount(patch_px + 1, True).gte(patch_px)
    return in_patch, change.mask()


def rule_marks(box: Box, before: Period, after: Period, rule: tuple) -> ee.Image | None:
    """Return an image of a box with two bands, for a comparison with a different map.

    `burned` is 1 where the rule calls a pixel burned in the period after the event.
    `clear` is 1 where the pixel has a clear view in that period. With no view before: None.
    """
    region = region_of(box)
    images = ee.ImageCollection(ASSET).filterBounds(region)
    view = _view(images, before, newest=True)
    if view is None:
        return None
    sums = {"geometry": region, "scale": SCALE_M, "maxPixels": 1e10}
    ratio = view.normalizedDifference(["B8A", "B12"])
    in_patch, clear = _one_look(ratio, images, after, (rule, sums))
    return in_patch.unmask(0).rename("burned").addBands(clear.unmask(0).rename("clear"))


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
    region = region_of(box)
    images = ee.ImageCollection(ASSET).filterBounds(region)
    view = _view(images, before, newest=True)
    days = [day for day, end in ends.items() if end > start]
    if view is None or not days:
        return {}
    ratio = view.normalizedDifference(["B8A", "B12"])
    sums = {"geometry": region, "scale": SCALE_M, "maxPixels": 1e10}
    hectares = ee.Image.pixelArea().divide(10_000)
    bands, counts = [hectares.rename("box")], []
    for day in days:
        counts.append(images.filterDate(start.isoformat(), ends[day].isoformat()).size())
        in_patch, clear = _one_look(ratio, images, (start, ends[day]), (rule, sums))
        bands.append(hectares.updateMask(in_patch).rename(f"burned_{day}"))
        bands.append(hectares.updateMask(clear).rename(f"clear_{day}"))
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


def new_ground(box: Box, before: Period, times: tuple, rule: tuple) -> dict | None:
    """Return the new burned ground of a box between two images, for the check of an advance.

    `times` has the time of view A and of view B. A pixel is burned in a view by the rule,
    against the view before the event. The answer has the burned hectares of view A, the new
    hectares of view B, the centre of each as (lat, lon), and the advance: a high percentile of
    the distance from a new pixel to the nearest pixel of view A, in metres.
    With no view before the event, or with no burned ground in one of the two: None.
    """
    region = region_of(box)
    images = ee.ImageCollection(ASSET).filterBounds(region)
    view = _view(images, before, newest=True)
    if view is None:
        return None
    sums = {"geometry": region, "scale": SCALE_M, "maxPixels": 1e10}
    ratio = view.normalizedDifference(["B8A", "B12"])
    hour = timedelta(hours=1)
    looks = [_one_look(ratio, images, (at - hour, at + hour), (rule, sums)) for at in times]
    (old, old_clear), (now, now_clear) = looks
    old = old.unmask(0).And(old_clear)
    new = now.unmask(0).And(now_clear).And(old_clear).And(old.Not())
    # The distance is in pixels, as a square. The largest distance is 1024 pixels.
    # Only a burned pixel in the box is the start of a distance, as for the areas and the centres.
    inside = old.clip(region).unmask(0)
    far_m = inside.fastDistanceTransform(1024).sqrt().multiply(SCALE_M).rename("far")
    hectares, place = ee.Image.pixelArea().divide(10_000), ee.Image.pixelLonLat()
    found = ee.Dictionary(
        {
            "areas": ee.Image.cat(
                [
                    hectares.updateMask(old).rename("old_ha"),
                    hectares.updateMask(new).rename("new_ha"),
                ]
            ).reduceRegion(reducer=ee.Reducer.sum(), **sums),
            "old": place.updateMask(old).reduceRegion(reducer=ee.Reducer.mean(), **sums),
            "new": place.updateMask(new).reduceRegion(reducer=ee.Reducer.mean(), **sums),
            "far": far_m.updateMask(new).reduceRegion(
                reducer=ee.Reducer.percentile([config.GROWTH_ADVANCE_PERCENT]), **sums
            ),
        }
    ).getInfo()
    if not found["areas"]["old_ha"] or not found["areas"]["new_ha"]:
        return None
    return {
        "old_ha": round(found["areas"]["old_ha"], 2),
        "new_ha": round(found["areas"]["new_ha"], 2),
        "old_place": (found["old"]["latitude"], found["old"]["longitude"]),
        "new_place": (found["new"]["latitude"], found["new"]["longitude"]),
        "advance_m": round(found["far"]["far"], 1),
    }


def joined(box: Box, before: Period, period: Period, rule: tuple) -> tuple | None:
    """Return the clear share of a box and its burned hectares, with each image of a period joined.

    This was the first definition of the burn curve: a pixel is burned if the rule calls it
    burned in a minimum of one image. It failed its hypothesis, because each image adds its
    errors (`docs/method.md` section 11.17). It stays only to make the table of that result.
    Only an image that covers all of the box counts. With no view before the event: None.
    """
    region = region_of(box)
    images = ee.ImageCollection(ASSET).filterBounds(region)
    view = _view(images, before, newest=True)
    if view is None:
        return None
    ratio = view.normalizedDifference(["B8A", "B12"])
    sums = {"geometry": region, "scale": SCALE_M, "maxPixels": 1e10}

    def flag(image: ee.Image) -> ee.Image:
        seen = _clear(image)
        raw = ratio.subtract(seen.normalizedDifference(["B8A", "B12"])).rename("change")
        median = raw.reduceRegion(reducer=ee.Reducer.median(), **sums).get("change")
        change = raw.subtract(ee.Image.constant(ee.Number(ee.Algorithms.If(median, median, 0))))
        burned = change.gte(rule[0]).And(seen.select("B8A").divide(10_000).lte(rule[1]))
        return burned.unmask(0).rename("burned").addBands(change.mask().rename("clear")).toByte()

    flags = images.filterDate(period[0].isoformat(), period[1].isoformat())
    flags = flags.filter(ee.Filter.contains(".geo", region)).map(flag)
    nothing = ee.ImageCollection([ee.Image.constant([0, 0]).rename(["burned", "clear"]).toByte()])
    ever = nothing.merge(flags).max()
    patch_px = round(config.BURN_PATCH_HA * 10_000 / SCALE_M**2)
    in_patch = ever.select("burned").selfMask().connectedPixelCount(patch_px + 1, True)
    hectares = ee.Image.pixelArea().divide(10_000)
    bands = [hectares.rename("box"), hectares.updateMask(ever.select("clear")).rename("clear")]
    bands.append(hectares.updateMask(in_patch.gte(patch_px)).rename("burned"))
    found = ee.Image.cat(bands).reduceRegion(reducer=ee.Reducer.sum(), **sums).getInfo()
    return round(found["clear"] / found["box"], 4), round(found["burned"], 2)
