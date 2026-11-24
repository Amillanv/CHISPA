"""All fixed values of the project: the region, the periods, the thresholds and the paths.

Each threshold goes in this file and in no other file.
Thus one file shows all the choices that can change a result.
The first part holds those choices. A marker line ends it. The second part holds the other values.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

# The Pantanal bounding box in degrees: west, south, east, north.
# We use it to request data. The biome border, not this box, selects data for results.
PANTANAL_BOX = (-59.5, -22.5, -54.5, -15.5)

# We set thresholds on the development year. The test year scored the merge one time.
# Each later part uses those two years to set its rules, and the year below as its test year.
DEVELOPMENT_YEAR = 2023
TEST_YEAR = 2024
PART_TEST_YEAR = 2025

# The years that have mapped fires in the store, with the role of each in the results.
YEAR_ROLES = {
    DEVELOPMENT_YEAR: "development year",
    TEST_YEAR: "test year of the merge",
    PART_TEST_YEAR: "test year of the later parts",
}

# --- FIRMS ---

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

# GOES-19 replaced GOES-16 as the east satellite. The bucket of GOES-16 has no files after
# 2025-04-07. From this day we read the raw files of GOES-19. The two have the same pixel grid.
GOES19_START = datetime(2025, 4, 7, tzinfo=UTC)

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

# 8: pixels that touch at a corner are one scar. 4: only pixels that share a side.
SCAR_CONNECTIVITY = 8

# The pixel of the grid on which we save the burn days, in degrees (approximately 445 m).
# The product has pixels of 463 m.
BURNDAY_PIXEL_DEG = 0.004

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

# --- Evaluation ---
# Tune these values only on the development year.

# A fire smaller than this is not counted in fire recall. Most of them are small scars
# with no burn day: pieces that the month split of the map makes.
EVAL_MIN_FIRE_HA = 10.0

# A detection matches a fire in time if its day is not farther than this from the
# burn days of the fire. Two burn day products agree to 7 days for 95 percent of cells.
# Two burned cells that touch are one fire if their burn days are not farther apart than this:
# we cannot divide in time what we cannot match in time.
EVAL_DAY_MARGIN = 7

# The scar map gives the month of an image. For 60 percent of the burned area that is one
# month after the burn, and almost never before it. Thus we look this many months back:
# for the burn day of a pixel, and for the month of a detection when a fire has no burn day.
EVAL_MONTHS_BEFORE = 1

# A detection matches a fire if a pixel of the fire is in the square of the footprint
# plus this margin, in metres.
EVAL_MARGIN_M = 250.0

# The limits of the fire size classes in hectares.
EVAL_SIZE_CLASSES_HA = (10.0, 100.0, 1000.0, 10000.0)

# --- Sentinel-2 ---

SENTINEL2_ASSET = "COPERNICUS/S2_SR_HARMONIZED"

# The scene classes of a pixel that a rule does not use: no data, defect, cloud shadow, water,
# cloud and cirrus. Water that dries decreases the burn ratio as a burn does.
SENTINEL2_NOT_CLEAR = (0, 1, 3, 6, 8, 9, 10)

# The scene classes that hide the ground from a person: no data, defect, cloud and cirrus.
# Cloud shadow is not in this list: the scene classes can give a new burn that class.
SENTINEL2_CLOUD = (0, 1, 8, 9, 10)

# The pixel size of the bands B8A and B12, in metres.
SENTINEL2_SCALE_M = 20

# --- Burn check ---

# The burn check asks Sentinel-2 if the ground at an event burned.
# The seed makes the same samples each time.
BURN_SEED = 1

# A box of the burn check is the box of the event plus this margin in metres. The margin is
# the reach of a GOES detection in the match rule: its footprint plus the match margin.
BURN_MARGIN_M = 1500.0

# The view before an event is not older than this many days before the first detection.
# The view after an event is not newer than this many days after the last detection.
BURN_DAYS = 30

# dNBR is the burn ratio before minus the burn ratio after.
# We count the burned area at each of these steps.
BURN_DNBR_STEPS = (0.1, 0.2, 0.3, 0.4)

# A burned pixel counts only in a patch of this many hectares or more.
BURN_PATCH_HA = 1.0

# A candidate rule also needs a dark ground after the event: a near infrared reflectance (band B8A)
# of one of these limits or less. A burn is dark. Bare ground and a dry field are bright.
BURN_DARK_STEPS = (0.15, 0.2, 0.25)

# The steps of the short-wave burn ratio, NBR2 = (B11 - B12) / (B11 + B12). A burn on grass
# changes this ratio more than it changes the burn ratio with near infrared.
BURN_NBR2_STEPS = (0.05, 0.1, 0.2, 0.3)

# The Monitor do Fogo map of a month can show a burn of the month before. Thus we read the months
# from the first detection of an event to this many months after its last detection.
MONITOR_MONTHS_AFTER = 1

# The steps of the change of the radar backscatter that we count, in decibels.
RADAR_DB_STEPS = (1.0, 2.0, 3.0)

# The setting of each candidate for the burned ground: the key of its measure and the minimum
# hectares. The box rule keeps the pair of the burn check. The Monitor map and radar have the
# setting with the largest difference between the found share and the no-fire share on the
# development year (table `burn_candidates`, set on 2023 on 2026-11-23).
# The dark rule and the short-wave rule have the setting with the largest agreement with the
# answers of a person on 2024 (`docs/method.md` section 11.16, set on 2026-11-23). On 2023 the
# dark rule had its largest difference at ("0.2/0.15", 1.0).
BURN_CANDIDATES: dict | None = {
    "box rule": ("0.3", 10.0),
    "dark rule": ("0.3/0.2", 1.0),
    "short-wave rule": ("nbr2:0.1/0.2", 1.0),
    "monitor": ("monitor", 1.0),
    "radar VV": ("VV/3.0", 25.0),
    "radar VH": ("VH/3.0", 25.0),
}

# The candidate that gives the burned ground of an event. The owner selected the dark rule on
# 2026-11-24, after the test of 2025: `docs/method.md` section 11.16 says why.
BURN_RULE = "dark rule"

# The burn curve gives the burned ground of an event at each clear view, to the last of these
# days after its first detection. The table gives the state at each of these days.
CURVE_DAYS = (5, 10, 20, 30)

# An event gets its curve when its last day is this many days in the past. An image is in
# Earth Engine some days after its scan. The number of days is an estimate.
CURVE_WAIT_DAYS = 5

# A request to Earth Engine that fails is sent again, to this number of times.
# Earth Engine refuses a request when too many run at one time.
EARTHENGINE_TRIES = 5

# The check of the advance needs an event that lasts this many days or more, and two views
# with this many days or more between them. A fire must move between the two views.
ADVANCE_MIN_DAYS = 6
ADVANCE_VIEW_DAYS = 5

# Two advances agree if the larger is not more than this number of times the smaller.
# Two directions agree if the angle between them is not more than this number of degrees.
ADVANCE_SAME_FACTOR = 2.0
ADVANCE_SAME_DEG = 45.0

# The rule says "burned" if the burned area of a box is one of these hectares or more.
BURN_HA_STEPS = (1.0, 10.0, 25.0)

# The dNBR step and the hectares that say "burned". Set them on the development year: the pair with
# the largest difference between the burned share of matched events and that of boxes with no fire.
# If two pairs are equal, the pair with the smaller area. Set on 2023 on 2026-11-22: two pairs
# had the difference 0.7071 (table `burn_check` of 2023).
BURN_DNBR_MIN: float | None = 0.3
BURN_HA_MIN: float | None = 10.0

# A box gives an answer only if this share of it, or more, has a clear view before and after.
BURN_MIN_CLEAR = 0.5

# The number of matched HIGH events, and of boxes with no fire, that give the two reference shares.
BURN_CONTROL = 100

# --- Image check ---

# The number of HIGH events with no match that a person examines, and the number of HIGH
# events with a match in the same sample. The person checks the answers of the burn check.
IMAGE_SAMPLE = 60
IMAGE_CONTROL = 30

# A picture must come from an image with less cloud than this percentage of its tile.
IMAGE_MAX_CLOUD = 20.0

# The ground size of one pixel of a picture in metres, and the largest side of a picture in pixels.
IMAGE_M_PER_PX = 10.0
IMAGE_MAX_PX = 2048

# The second look of the image check: the events of the first look again, and this number of
# no-fire boxes. A no-fire box shows how frequently a person says "burned" with no fire.
IMAGE_NO_FIRE = 60

# A year with no first look has a smaller sample for the second look: this number of boxes
# from the start of each group of the burn check.
IMAGE_TEST_SAMPLE = {"unmatched": 30, "matched": 20, "no fire": 30}

# A picture of the second look needs this share of its box with no cloud, or more. The first look
# used the cloud of the full image tile: it gave no picture for some boxes with a clear sky.
IMAGE_MIN_CLEAR = 0.8

# The second look has one more picture: a later view, this many days or more after the picture
# after the event, and not later than this many days after the last detection.
# A burn stays in the later view. A shadow or water does not.
IMAGE_LATER_MIN_DAYS = 5
IMAGE_LATER_DAYS = 60

# Events that are in no comparison with the answers of the person: the person saw an opinion on
# them before the second look (`docs/method.md` section 11.10).
IMAGE_NOT_BLIND = ("20240016701", "20240006447", "20240008269")

# --- Measured growth ---

# The advance of a step is this percentile of the distances of its pixels to the older pixels.
GROWTH_ADVANCE_PERCENT = 90

# A pixel is a new pixel if it is farther than this from each older pixel, in metres. Set it on the
# development year: the 90th percentile of the advance of the steps with less than GROWTH_SHORT_H
# hours from the pass before, to the next 50 m. Those steps show the error of the positions.
# Set on 2023 on 2026-11-22: that percentile was 836.55 m (table `growth_steps` of 2023).
GROWTH_FLOOR_M = 850.0
GROWTH_SHORT_H = 2.0

# A step has a speed only if the time from the pass before is this many hours or more.
GROWTH_SPEED_MIN_H = 6.0

# The limits of the classes of the time between two passes, in hours.
GROWTH_HOUR_CLASSES = (0.0, 2.0, 6.0, 18.0, 24.5)

# --- Visibility ---

# A fire has a low examined share if GOES examined its place in less than this share of its scans.
VISIBILITY_FIRE_LOW = 0.5
# A day is a day of cloud if GOES examined less than this share of the mask window.
VISIBILITY_DAY_LOW = 0.25

# A raw GOES file is in the NOAA bucket this long after the start of its scan (`docs/sources.md`
# section 8.10). We did not have a recorded mask before that time.
GOES_RAW_DELAY = timedelta(minutes=10)

# --- Severity ---

# The last year of the land cover map. An event uses the map of the year before it,
# not later than this year.
LANDCOVER_LAST_YEAR = 2024

# The side of a cell of the layer grid, in scar pixels: approximately 300 m.
LAYER_CELLS = 10

# The MapBiomas land cover classes in groups. `docs/sources.md` section 8.14 gives the class names.
COVER_GROUPS = {
    "forest": (3, 5, 6, 49),
    "savanna": (4,),
    "wetland": (11,),
    "grassland": (12,),
    "pasture": (15,),
    "farming": (9, 20, 21, 39, 40, 41, 46, 47, 48, 62),
    "built": (24, 30),
    "water": (31, 33),
}

# The points of each part of the severity. The sum of the largest values is 100.
# The points of the land cover, of the people and of the land are choices of the owner.
# They are not measured.
SEVERITY_POWER_POINTS = 20
SEVERITY_EXTENT_POINTS = 15
SEVERITY_ADVANCE_POINTS = 15
SEVERITY_COVER_POINTS = {
    "forest": 20,
    "savanna": 16,
    "wetland": 16,
    "built": 20,
    "grassland": 12,
    "pasture": 8,
    "farming": 8,
    "water": 0,
    "other": 4,
}
SEVERITY_PEOPLE_POINTS = 15
SEVERITY_LAND_POINTS = 15  # A detection in protected or indigenous land.
SEVERITY_LAND_NEAR_POINTS = 8  # Such land is not farther than SEVERITY_NEAR_KM.
SEVERITY_NEAR_KM = 5.0

# A value gets one third of its points for each step that it reaches.
# Fire power in megawatts, extent in kilometres and advance in metres: set them on the development
# year, as the 50th, 75th and 90th percentile of the events with a value (table `severity_inputs`).
# Set on 2023 on 2026-11-23, with the alerts as they were at the evaluation time.
SEVERITY_POWER_STEPS_MW: tuple | None = (54.81, 83.57, 108.7)
SEVERITY_EXTENT_STEPS_KM: tuple | None = (2.2, 4.42, 8.61)
SEVERITY_ADVANCE_STEPS_M: tuple | None = (1263.59, 1852.71, 2745.11)
# The number of people in the square around a detection. A choice of the owner.
SEVERITY_PEOPLE_STEPS = (10.0, 100.0, 1000.0)
# The side of that square in layer cells: approximately 10 km.
SEVERITY_PEOPLE_CELLS = 33

# The check of the severity uses the detections that were available this many hours
# after the first detection of an event.
SEVERITY_EVAL_HOURS = 24.0
SEVERITY_SCORE_CLASSES = (0.0, 25.0, 50.0, 75.0, 100.1)

# --- Confidence ---

# The penalty on the weights of the confidence model. A larger value gives smaller weights.
# Set it on the test year of the merge, which is the tuning year of this part.
CONFIDENCE_PENALTY = 0.001

# The fire activity near an event: the detections of this many days before the day of its first
# alert, in the cell of the first detection and in the 8 cells around it. The side of a cell
# is in degrees (approximately 11 km).
CONFIDENCE_NEAR_DAYS = 7
CONFIDENCE_NEAR_CELL_DEG = 0.1

# === The values above this line can change a result. The configuration hash covers them. ===
# The values below this line change no number in a result table.

# --- Paths and downloads ---

DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "raw"
STORE_PATH = DATA_DIR / "chispa.sqlite"

# The public bucket with a copy of all raw files. A fork can use a different bucket.
BUCKET = "chispa_raw"

RESULTS_DIR = Path("results")

# The pictures of the image check. Earth Engine can make them again, thus they are not raw files.
IMAGE_DIR = DATA_DIR / "images"

# Seconds between two requests, to stay far below the limit of the API.
FIRMS_PAUSE_S = 1.0

# The side of a download tile in pixels. Earth Engine limits the size of one request.
SCAR_TILE_PX = 2048

# --- Live operation ---

# The first day of the live logs. A fetch of the archive files stops on the day before it:
# from this day, the detections come from the poller, with the time when we first saw them.
LIVE_START = datetime(2026, 11, 20, tzinfo=UTC)

# One pass of the poller reads each GOES scan and each INPE file of this time before it that no
# pass read. Thus a shorter stop of the poller loses no GOES scan. INPE removes a file of
# 10 minutes after some days: its oldest file was 3.8 days old (`docs/sources.md` section 8.10).
# Thus a stop of more than 3 days can lose INPE files.
LIVE_LOOKBACK = timedelta(days=4)

# One live request to FIRMS gives the rows of this many days: the maximum of the API.
# Thus a stop of the poller of less than 4 days loses no FIRMS row.
LIVE_FIRMS_DAYS = 5

# The poller runs each 5 minutes. Late: this time with no pass in which all sources answered.
# A row that a pass first saw later than this after its publication came after a stop.
LIVE_POLL_LATE = timedelta(minutes=15)

# The time from the publication of a scan or a file to the next pass, in normal operation.
# A row that a pass saw late gets its publication time plus this estimate. It is not a
# measurement: the poller runs each 5 minutes, thus the mean wait is approximately half of that.
LIVE_NORMAL_WAIT = timedelta(minutes=3)

# A live log of a day can get new rows for this long after the start of that day: a pass reads
# back `LIVE_LOOKBACK`, and a FIRMS request gives `LIVE_FIRMS_DAYS`. Then the log is complete.
LIVE_COMPLETE_AFTER = max(LIVE_LOOKBACK + timedelta(days=1), timedelta(days=LIVE_FIRMS_DAYS))

# --- Tools ---

# The largest radius that a tool accepts, in kilometres. The Pantanal box is 780 km long.
TOOL_MAX_RADIUS_KM = 500.0

# The largest number of detections that a tool returns for one event.
TOOL_MAX_DETECTIONS = 200

# The newest passes that the event record shows. Each pass that made the level go up is also shown.
TOOL_MAX_PASSES = 60

# The largest number of steps that the activity tool returns: 7 days in steps of 10 minutes.
TOOL_MAX_STEPS = 1008

# --- Dashboard ---

# The page asks for the events in a circle around this centre. The radius reaches each corner
# of the Pantanal box, and it is the largest radius that a tool accepts.
DASHBOARD_CENTRE = (-19.0, -57.0)
DASHBOARD_RADIUS_KM = 500.0

# An event is on the page if one of its detections became available in these hours
# before the as-of time.
DASHBOARD_SINCE_HOURS = 24.0

# The windows of the history band, as (hours, step hours). The page opens with the second.
DASHBOARD_WINDOWS = ((72.0, 1.0), (168.0, 3.0), (720.0, 12.0))

# In live mode the page gets the data again after this time.
DASHBOARD_REFRESH = timedelta(minutes=5)

# The local time of the Pantanal. Mato Grosso do Sul and Mato Grosso had the same time, UTC-4,
# at each hour from 2020 to 2026 (`docs/sources.md` section 8.16).
DASHBOARD_TIME_ZONE = "America/Campo_Grande"

# Moments of recorded data that the page offers for a replay: days with many events.
DASHBOARD_REPLAYS = (
    datetime(2024, 10, 15, 13, 50, tzinfo=UTC),
    datetime(2024, 9, 10, 18, 0, tzinfo=UTC),
    datetime(2024, 8, 22, 0, 0, tzinfo=UTC),
    datetime(2023, 11, 15, 18, 0, tzinfo=UTC),
)
