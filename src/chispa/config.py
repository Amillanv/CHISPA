"""All fixed values of the project: the region, the periods and the paths.

Each threshold goes in this file and in no other file.
Thus one file shows all the choices that can change a result.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

# The Pantanal bounding box in degrees: west, south, east, north.
# We use it to request data. The biome border, not this box, selects data for results.
PANTANAL_BOX = (-59.5, -22.5, -54.5, -15.5)

# We set thresholds on the development year and report results on the test year.
DEVELOPMENT_YEAR = 2023
TEST_YEAR = 2024

DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "raw"
STORE_PATH = DATA_DIR / "chispa.sqlite"

# The public bucket with a copy of all raw files. A fork can use a different bucket.
BUCKET = "chispa_raw"

# --- FIRMS ---

# Seconds between two requests, to stay far below the limit of the API.
FIRMS_PAUSE_S = 1.0

# FIRMS does not give the time when a detection became available.
# These delays are estimates, not measurements. They change each delay result.
# Polar-orbit sensors: FIRMS states "within 3 hours of the observation".
# GOES: one raw file was available 10 minutes after the scan start. We add time for FIRMS.
AVAILABLE_DELAY = {
    "viirs": timedelta(hours=3),
    "modis": timedelta(hours=3),
    "abi": timedelta(minutes=30),
    "avhrr": timedelta(hours=3),  # No statement from INPE. We use the polar-orbit value.
}

# MODIS gives confidence as a percentage. These limits come from the MODIS fire user guide.
MODIS_NOMINAL_FROM = 30
MODIS_HIGH_FROM = 80

# The radius of a GOES pixel over the Pantanal in metres. This is an estimate.
# The pixel is 2.0 km below the satellite and larger at the angle of the Pantanal.
GOES_FOOTPRINT_M = 1250.0

# GOES mask classes that FIRMS gives: 10 good, 11 saturated, 30 and 31 the same after
# the time filter. We give all of them "nominal" until the 2023 data shows a difference.
GOES_CONFIDENCE = {10: "nominal", 11: "nominal", 30: "nominal", 31: "nominal"}

# FIRMS has no GOES-16 rows between these two scan times. We fill the gap from raw NOAA files.
# The start is the first absent scan. The end is the first scan that FIRMS has again.
GOES_GAP_START = datetime(2024, 9, 28, 15, 0, tzinfo=UTC)
GOES_GAP_END = datetime(2024, 11, 16, 23, 50, tzinfo=UTC)

# --- INPE ---

# INPE gives no pixel size. These radii in metres are estimates: the pixel size below
# the satellite. A real pixel is larger at the edge of the swath.
INPE_FOOTPRINT_M = {"viirs": 375.0, "modis": 1000.0, "avhrr": 1100.0, "abi": GOES_FOOTPRINT_M}

# --- MapBiomas Fogo ---

SCAR_ASSET = (
    "projects/mapbiomas-public/assets/brazil/fire/collection5_1/"
    "mapbiomas_fire_collection51_monthly_burned_v1"
)

# The grid of the MapBiomas asset: the size of a pixel in degrees (30 m) and the
# west and north edges of the full grid. These values come from the asset.
SCAR_PIXEL_DEG = 0.0002694945852358564
SCAR_ORIGIN = (-74.54354974916409, 6.761619143567639)

# The side of a download tile in pixels. Earth Engine limits the size of one request.
SCAR_TILE_PX = 2048

# 8: pixels that touch at a corner are one scar. 4: only pixels that share a side.
SCAR_CONNECTIVITY = 8

# --- Fusion ---
# These values are a first proposal. Tune them only on the development year.

# The fusion puts detections on a grid of cells. This is the side of a cell in degrees
# (approximately 550 m). The join distance is thus approximate by up to one cell.
FUSION_CELL_DEG = 0.005

# A detection occupies its footprint plus this margin, in metres.
FUSION_MARGIN_M = 500.0

# Two detections that occupy the same cell are one event if their observation times
# are not farther apart than this.
FUSION_WINDOW = timedelta(hours=24)

# Detections of one platform are one pass if their times are not farther apart than this.
# FIRMS and INPE give times of the same pass that differ by one or two minutes.
PASS_GAP = timedelta(minutes=30)

# GOES makes one scan each 10 minutes. FIRMS gives the start of the scan. INPE gives a time
# approximately 7 minutes later. We move each GOES time back to the start of its scan.
GOES_SCAN = timedelta(minutes=10)
