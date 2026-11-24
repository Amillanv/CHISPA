"""The monthly burned area of MapBiomas Monitor do Fogo, through Google Earth Engine.

The annual map of burn scars comes in the next year. This map comes some weeks after each month.
It is a candidate for the burned ground of an event, and a reference for a year with no annual map.
"""

from datetime import datetime

import ee

from chispa import config

ASSET = "projects/mapbiomas-public/assets/brazil/fire/monitor/mapbiomas_fire_monthly_burned_v1"
SCALE_M = 30  # The pixel size of the images of the asset.

Box = tuple[float, float, float, float]  # south, west, north, east


def month_names(first: datetime, last: datetime) -> list[str]:
    """Return the image name of each month from the first detection to the months after the last."""
    year, month = first.year, first.month
    end = last.year * 12 + last.month + config.MONITOR_MONTHS_AFTER
    names = []
    while year * 12 + month <= end:
        names.append(f"brazil-{year}-{month}")
        year, month = (year, month + 1) if month < 12 else (year + 1, 1)
    return names


def burned_ha(box: Box, first: datetime, last: datetime) -> float:
    """Return the hectares of a box that the map gives as burned in the months of an event."""
    south, west, north, east = box
    region = ee.Geometry.Rectangle([west, south, east, north])  # Earth Engine uses lon, lat.
    months = ee.ImageCollection(ASSET).filter(ee.Filter.inList("name", month_names(first, last)))
    burned = months.map(lambda image: image.unmask(0).gt(0)).max()
    area = ee.Image.pixelArea().divide(10_000).updateMask(burned).rename("burned")
    found = area.reduceRegion(ee.Reducer.sum(), region, SCALE_M, maxPixels=1e9).getInfo()
    return round(float(found.get("burned") or 0), 2)
