"""Protected land and indigenous land, from the World Database on Protected Areas (WDPA).

A fire in or near such land has a larger effect. The database is a list of areas with outlines.
We save two grids with the identifier of the area in each cell, one for indigenous land and
one for other protected land, and the name of each area.
"""

import json
from pathlib import Path

import ee
import numpy as np

from chispa import config
from chispa.earthengine import read_grid
from chispa.grid import Grid

ASSET = "WCMC/WDPA/current/polygons"
KINDS = ("indigenous", "protected")


def download(project: str, raw_dir: Path, grid: Grid) -> list[Path]:
    """Save the two grids and the names of the areas, and return the paths."""
    folder = raw_dir / "protected"
    paths = [folder / "areas.npz", folder / "areas.json"]
    if all(path.exists() for path in paths):
        return paths
    ee.Initialize(project=project)
    west, south, east, north = config.PANTANAL_BOX
    areas = ee.FeatureCollection(ASSET).filterBounds(
        ee.Geometry.Rectangle(west, south, east, north)
    )
    # An international label, such as a biosphere reserve, covers a very large region.
    areas = areas.filter(ee.Filter.eq("DESIG_TYPE", "National"))
    is_indigenous = ee.Filter.stringContains("DESIG_ENG", "Indigenous")
    parts = {
        "indigenous": areas.filter(is_indigenous),
        "protected": areas.filter(is_indigenous.Not()),
    }
    grids = {
        kind: read_grid(
            part.reduceToImage(["SITE_ID"], ee.Reducer.first()).unmask(0).toInt32(), grid
        )
        for kind, part in parts.items()
    }
    fields = ["SITE_ID", "NAME", "DESIG_ENG"]
    rows = areas.reduceColumns(ee.Reducer.toList(len(fields)), fields).get("list").getInfo()
    folder.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(paths[0], **grids)
    paths[1].write_text(json.dumps({str(int(row[0])): row[1:] for row in rows}, ensure_ascii=False))
    return paths


def read(raw_dir: Path) -> tuple[dict[str, np.ndarray], dict[int, str]]:
    """Return the grid of each kind, and the name of each area with its designation."""
    folder = raw_dir / "protected"
    if not (folder / "areas.npz").exists():
        raise RuntimeError("Run `chispa fetch protected` first.")
    grids = np.load(folder / "areas.npz")
    names = json.loads((folder / "areas.json").read_text())
    return (
        {kind: grids[kind] for kind in KINDS},
        {int(site): f"{name} ({designation})" for site, (name, designation) in names.items()},
    )
