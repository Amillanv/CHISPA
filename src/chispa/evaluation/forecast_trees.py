"""The fit of the saved trees of the live growth forecast: the trees of all development years.

A live forecast loads its trees from a file (`forecast_model.py`). This module fits them from
the rows of all development years with their answers, and it saves them with a mark of what
made them: the configuration, the code, the library and the detections of those years in the
store. The command `chispa forecast --trees` runs it: some minutes.
`docs/method.md` section 11.29 gives the rule.
"""

import hashlib
import sqlite3
from pathlib import Path

import sklearn

from chispa import config, forecast_model, front_inputs, fronts
from chispa.config_hash import config_hash
from chispa.evaluation import forecast, forecast_run
from chispa.evaluation import fronts as steps
from chispa.grid import pantanal_grid
from chispa.sources import border

# The detections that the trees learn from: the mark of the saved trees has a hash of them.
TRAINING = """
SELECT observed_at, available_at, lat, lon, frp_mw, platform FROM detections
WHERE sensor_family = ? AND source = ? AND observed_at >= ? AND observed_at < ? ORDER BY id
"""


def mark(store_path: Path) -> str:
    """Return a mark of what makes the trees: the configuration, the code of the rows and of the
    trees, the version of scikit-learn, and the detections of the development years in the store.

    A raw file does not change (`docs/sources.md` section 8.7), thus the mark does not read the
    raw layers. A forecast file has this mark: a later score can group the files by their trees.
    """
    modules = (fronts, front_inputs, forecast_model, steps, forecast, forecast_run)
    # This module has the fit of the saved trees: its code is also in the mark.
    code = "".join(Path(file).read_text() for file in (*(m.__file__ for m in modules), __file__))
    years = (f"{min(config.FRONT_YEARS)}-01-01", f"{max(config.FRONT_YEARS) + 1}-01-01")
    found = hashlib.sha256(f"{code}{sklearn.__version__}".encode())
    store = sqlite3.connect(store_path)
    for row in store.execute(TRAINING, (fronts.SENSOR_FAMILY, fronts.SOURCE, *years)):
        found.update(repr(row).encode())
    return config_hash() + found.hexdigest()[:12]


def fit(store_path: Path, raw_dir: Path) -> str:
    """Fit the trees of each question from all development years, save them, and return their
    mark. A live forecast loads the saved file."""
    years = config.FRONT_YEARS
    rings = border.read_rings(raw_dir / "border" / "pantanal.geojson")
    in_biome = border.rasterize(rings, pantanal_grid())
    cases = forecast_run.year_cases(
        {year: forecast.year_rows(year, store_path, raw_dir, in_biome) for year in years}
    )
    models, names = {}, {}
    for key, case in cases[years[0]].items():
        train = forecast_run.training(cases, years, key)
        models[key] = forecast_model.fit_trees(train["x"], train["y"], train["years"])
        names[key] = case["names"]
    trees = mark(store_path)
    forecast_model.save_trees(models, names, trees)
    return trees
