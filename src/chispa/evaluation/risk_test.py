"""The rows of the test year of the growth risk: a year with no annual map.

The annual map of a year comes in the next year. The Monitor map comes some weeks after each
month. This module makes the fires of the test year from the Monitor map, with the rule of the
annual map, and the rows of its alerts with the inputs of the models.
`docs/method.md` section 11.25 gives the rules.
"""

import calendar
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np

from chispa import config, fires
from chispa.evaluation.confidence import MOMENTS, year_rows
from chispa.evaluation.inputs import fire_fields
from chispa.evaluation.match import Fields, match
from chispa.evaluation.risk import seen_first, sized_rows
from chispa.evaluation.risk_inputs import add_model_inputs
from chispa.evaluation.run import biome_detections
from chispa.grid import pantanal_grid
from chispa.sources import border, burnday, monitor, scars


def monitor_fires(year: int, raw_dir: Path, data_dir: Path) -> tuple[np.ndarray, Fields, int]:
    """Return the fire grid and the fires of one year from the Monitor map, and its last month.

    The rule for a fire is that of the annual map (`fires.py`). The step needs some gigabytes
    of memory and some minutes, thus its result is a file, as the fire grid of the annual map.
    """
    grid = pantanal_grid()
    months, last = monitor.read_year(year, raw_dir, grid)
    path = data_dir / "fires_monitor" / f"{year}-{last:02d}.npz"
    if not path.exists():
        rings = border.read_rings(raw_dir / "border" / "pantanal.geojson")
        months *= border.rasterize(rings, grid)
        days, coarse = burnday.read_year(year, raw_dir), burnday.burnday_grid()
        found, numbers = fires.find_fires(months, scars.find_scars(months), grid, days, coarse)
        fields = fire_fields(found, year)
        del fields["year"]
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, numbers=numbers, **fields)
    saved = np.load(path)
    fields = {name: saved[name] for name in saved.files if name != "numbers"} | {"year": year}
    return saved["numbers"], fields, last


def known_until(year: int, last_month: int) -> datetime:
    """Return the last time of a moment whose outcome the map can have.

    An outcome is known the delay of the recalibration after the moment of its alert, and the
    map ends with the last day of its last month.
    """
    end = date(year, last_month, calendar.monthrange(year, last_month)[1]) + timedelta(days=1)
    start_of_next = datetime(end.year, end.month, end.day, tzinfo=UTC)
    return start_of_next - timedelta(days=config.RISK_RECALIBRATION_DELAY_DAYS)


def monitor_part(year: int, store_path: Path, raw_dir: Path) -> dict:
    """Return the rows of the test year: sizes from the Monitor map, and the inputs of the models.

    Only an alert with a known outcome is in the test. The rows have no input of a group that
    no model has: the sources of some groups do not have the test year.
    """
    numbers, fields, last = monitor_fires(year, raw_dir, store_path.parent)
    until = known_until(year, last)
    detections = biome_detections(year, store_path, raw_dir)
    pairs = match(detections, numbers, pantanal_grid(), fields)
    rows, _ = year_rows(year, store_path, raw_dir, (detections, pairs, fields))
    first = seen_first(detections, pairs, fields)
    sized = {}
    for moment in MOMENTS:
        kept = [row for row in rows[moment] if row["at"] <= until.timestamp()]
        add_model_inputs(kept, detections, raw_dir, year, until.date() + timedelta(days=5))
        sized[moment] = sized_rows(kept, first, fields["area_ha"])
        for row in sized[moment]:
            del row["positions"]
    return {"rows": sized, "area_ha": fields["area_ha"], "until": until}
