"""The saved trees of the live growth forecast: the trees of all development years.

A live forecast needs the trees at once, and a fit needs some minutes. This module fits them
one time and saves them in a file with a mark of what made them. When the configuration, the
code, the library or a detection of the development years changes, the mark is not that of the
file, and the trees must be fitted again. `docs/method.md` section 11.29 gives the rule.
"""

import hashlib
import pickle
import sqlite3
from pathlib import Path

import sklearn

from chispa import config, fronts
from chispa.evaluation import forecast, forecast_run, front_inputs
from chispa.evaluation import fronts as steps
from chispa.evaluation.report import config_hash
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
    raw layers. After a new download of a layer of a development year, delete the saved file.
    """
    modules = (fronts, steps, front_inputs, forecast, forecast_run)
    code = "".join(Path(module.__file__).read_text() for module in modules)
    years = (f"{min(config.FRONT_YEARS)}-01-01", f"{max(config.FRONT_YEARS) + 1}-01-01")
    found = hashlib.sha256(f"{code}{sklearn.__version__}".encode())
    store = sqlite3.connect(store_path)
    for row in store.execute(TRAINING, (fronts.SENSOR_FAMILY, steps.SOURCE, *years)):
        found.update(repr(row).encode())
    return config_hash() + found.hexdigest()[:12]


def current(store_path: Path) -> dict | None:
    """Return the saved trees if their mark is the mark of now. None: they must be fitted again."""
    path = config.FORECAST_MODELS_PATH
    if path.exists():
        saved = pickle.loads(path.read_bytes())
        if saved["config"] == mark(store_path):
            return saved
    return None


def fitted(store_path: Path, raw_dir: Path) -> dict:
    """Return the trees of each question and their input names, from all development years.

    A saved file gives them, if the configuration, the code and the detections that made it
    are those of now. If not, this fits the trees again and saves them: some minutes.
    """
    saved = current(store_path)
    if saved is not None:
        return saved
    path, years = config.FORECAST_MODELS_PATH, config.FRONT_YEARS
    rings = border.read_rings(raw_dir / "border" / "pantanal.geojson")
    in_biome = border.rasterize(rings, pantanal_grid())
    cases = forecast_run.year_cases(
        {year: forecast.year_rows(year, store_path, raw_dir, in_biome) for year in years}
    )
    saved = {"config": mark(store_path), "models": {}, "names": {}}
    for key, case in cases[years[0]].items():
        train = forecast_run.training(cases, years, key)
        saved["models"][key] = forecast.fit_trees(train["x"], train["y"], train["years"])
        saved["names"][key] = case["names"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pickle.dumps(saved))
    return saved
