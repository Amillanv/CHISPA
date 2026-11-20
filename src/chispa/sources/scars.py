"""MapBiomas Fogo burn scars through Google Earth Engine.

The burn scars are the ground truth of the evaluation.
At this time the module only does a check of the access. The download is not built.
"""

import ee

from chispa import config


def check_access(project: str) -> list[str]:
    """Return the band names for the development year and the test year.

    Earth Engine uses the Google login on this computer. README.md gives the setup.
    """
    ee.Initialize(project=project)
    available = ee.Image(config.SCAR_ASSET).bandNames().getInfo()
    wanted = [f"burned_monthly_{year}" for year in (config.DEVELOPMENT_YEAR, config.TEST_YEAR)]
    absent = [name for name in wanted if name not in available]
    if absent:
        raise RuntimeError(f"The MapBiomas asset has no band {absent}.")
    return wanted
