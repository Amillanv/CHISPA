"""Sentinel-1 radar through Google Earth Engine: how much of a box changed its backscatter.

Radar sees the ground through cloud, and a burn can change the backscatter.
This module measures the changed area of a box, as a candidate for the burned ground of an event.
One orbit views the Pantanal each 12 days: `docs/sources.md` section 8.17.
"""

from datetime import datetime

import ee

from chispa import config

ASSET = "COPERNICUS/S1_GRD"
BANDS = ("VV", "VH")
SCALE_M = 20

Box = tuple[float, float, float, float]  # south, west, north, east
Period = tuple[datetime, datetime]


def changed_areas(box: Box, before: Period, after: Period) -> dict[str, float]:
    """Return the hectares of a box where the backscatter changed by each step or more.

    The change of a pixel is the mean of the scenes after minus the mean of the scenes before,
    in decibels, minus the median change of the box: rain changes all of the box.
    An increase and a decrease count. A pixel counts only in a patch of the minimum size.
    The key is the band and the step, for example "VH/2.0". `scenes` is the smaller number
    of scenes of the two periods. With no scene in a period, there is no other key.
    """
    south, west, north, east = box
    region = ee.Geometry.Rectangle([west, south, east, north])  # Earth Engine uses lon, lat.
    scenes = (
        ee.ImageCollection(ASSET)
        .filterBounds(region)
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .select(list(BANDS))
    )
    first = scenes.filterDate(before[0].isoformat(), before[1].isoformat())
    last = scenes.filterDate(after[0].isoformat(), after[1].isoformat())
    counts = ee.List([first.size(), last.size()]).getInfo()
    if min(counts) == 0:
        return {"scenes": 0}
    raw = last.mean().subtract(first.mean())
    sums = {"geometry": region, "scale": SCALE_M, "maxPixels": 1e9}
    median = raw.reduceRegion(reducer=ee.Reducer.median(), **sums)
    change = raw.subtract(median.toImage(list(BANDS))).abs()
    hectares = ee.Image.pixelArea().divide(10_000)
    patch_px = round(config.BURN_PATCH_HA * 10_000 / SCALE_M**2)
    keys = [f"{band}/{step}" for band in BANDS for step in config.RADAR_DB_STEPS]
    bands = []
    for number, key in enumerate(keys):
        band, step = key.split("/")
        high = change.select(band).gte(float(step)).selfMask()
        in_patch = high.connectedPixelCount(patch_px + 1, True).gte(patch_px)
        bands.append(hectares.updateMask(in_patch).rename(f"area_{number}"))  # No point in a name.
    found = ee.Image.cat(bands).reduceRegion(reducer=ee.Reducer.sum(), **sums).getInfo()
    areas = {key: round(found[f"area_{number}"], 2) for number, key in enumerate(keys)}
    return {"scenes": min(counts), **areas}
