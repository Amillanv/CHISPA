"""All fixed values of the project: the region, the periods and the paths.

Each threshold goes in this file and in no other file.
Thus one file shows all the choices that can change a result.
"""

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
