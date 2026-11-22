"""Make all the result tables of one fused year.

The evaluation runs after the fusion. It reads the store, the fire grid and the biome border.
"""

import sqlite3
from pathlib import Path

import numpy as np

from chispa.evaluation.events import event_table, split_table
from chispa.evaluation.inputs import load_detections, load_fires
from chispa.evaluation.match import isolated, match
from chispa.evaluation.recall import configurations, gain_table, measure, size_table
from chispa.grid import pantanal_grid
from chispa.sources import border


def evaluate(year: int, store_path: Path, raw_dir: Path) -> dict[str, list[dict]]:
    """Return the result tables of one fused year."""
    store = sqlite3.connect(store_path)
    grid = pantanal_grid()
    detections = load_detections(store, year)
    in_biome = border.rasterize(border.read_rings(raw_dir / "border" / "pantanal.geojson"), grid)
    rows, cols = grid.rows_cols(detections["lat"], detections["lon"])
    keep = in_biome[rows, cols]
    del in_biome
    detections = {name: values[keep] for name, values in detections.items()}
    numbers = np.load(store_path.parent / "fires" / f"{year}.npz")["numbers"]
    fires = load_fires(store, year)
    pairs = match(detections, numbers, grid, fires)
    fires["isolated"] = isolated(pairs, fires)
    chosen = configurations(detections)
    final_level = dict(store.execute("SELECT id, level FROM events"))
    return {
        "configurations": [
            measure(name, selection, detections, pairs, fires) for name, selection in chosen.items()
        ],
        "fire_sizes": size_table(detections, pairs, fires, chosen),
        "fire_events": split_table(detections, pairs, fires),
        "events": event_table(detections, pairs, fires, final_level),
        "merge_gain": gain_table(detections, pairs, fires),
    }
