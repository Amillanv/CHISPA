"""Write the result tables as CSV files and as one summary document.

Code makes each number in the summary. A person does not edit the summary by hand.
This module also gives the one format of a share and of a percentile in all tables.
"""

import csv
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from chispa import config
from chispa.config_hash import config_hash

# The file of a year with the stamp of each of its tables: the configuration and the day of the run.
# A stamp in each row of a table made each row new at each run, also with no new value.
STAMPS = "stamps.csv"

LIMITS = """Limits of these results:

- The sources are satellites only. There are no camera detections or community reports.
- A fire is a group of burned cells that touch and burned in near days (`docs/method.md`).
- The burn day of a fire is uncertain by some days. A fire with no burn day has only a month.
- The MODIS orbits drift. The effect on the burn days of late 2024 is not published.
- A delay is relative to the first detection from all sources, not to the start of the fire.
- Only isolated fires give a delay. `delay_fires` is their number. It is a small sample.
- The precision against the map is 1 minus the unmatched share. It is a lower limit:
  an unmatched detection is not always a false alarm. The fire can be too small for the map.
- A fire that burned for many days matches the detections of all those days.
- GOES has no low-probability detections, and has holes in late September to November 2024.
- The availability delay of each sensor family is an estimate in `config.py`.
- A fire in January can have detections in December of the year before. They cannot match it.
- A detection of December that became available in January is in the tables of the new year
  (`first_day`). From 2026-11-26 the match has the year, and such a detection matches no fire.
"""


def share(part: float, total: float) -> float | None:
    """Return part divided by total, or no value if the total is zero."""
    return round(float(part) / float(total), 4) if total else None


def percentile(values: np.ndarray, percent: int) -> float | None:
    """Return a percentile of the values, or no value if there are none."""
    return round(float(np.percentile(values, percent)), 2) if len(values) else None


def read_stamps(folder: Path) -> dict[str, dict[str, str]]:
    """Return, for each table of one year, the configuration hash and the day of its run."""
    path = folder / STAMPS
    if not path.exists():
        return {}
    with path.open(newline="") as file:
        return {row.pop("table"): row for row in csv.DictReader(file)}


def write_tables(tables: dict[str, list[dict]], year: int, results_dir: Path) -> None:
    """Save each table of one year as a CSV file, and its stamp in the stamp file of the year.

    The stamp of a table that this run does not make stays as it is.
    """
    folder = results_dir / str(year)
    folder.mkdir(parents=True, exist_ok=True)
    for name, rows in tables.items():
        with (folder / f"{name}.csv").open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    stamp = {"config": config_hash(), "run_date": datetime.now(UTC).date().isoformat()}
    stamps = read_stamps(folder) | dict.fromkeys(tables, stamp)
    with (folder / STAMPS).open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["table", *stamp])
        writer.writeheader()
        writer.writerows({"table": name, **stamps[name]} for name in sorted(stamps))


def write_summary(results_dir: Path) -> None:
    """Make `SUMMARY.md` again from all the CSV files in the results folder."""
    lines = ["# Results", "", "Code makes this file. Do not edit it by hand.", ""]
    for folder in sorted(path for path in results_dir.iterdir() if path.is_dir()):
        # A year with no role has no map of burn scars: only the tables that need no map.
        role = config.YEAR_ROLES.get(int(folder.name), "year with no map of burn scars")
        lines += [f"## {folder.name} ({role})", ""]
        stamps = read_stamps(folder)
        for path in sorted(folder.glob("*.csv")):
            if path.name == STAMPS:
                continue
            with path.open(newline="") as file:
                rows = list(csv.DictReader(file))
            columns, stamp = list(rows[0]), stamps[path.stem]
            # The year is in the heading. Thus a link to one table of one year is possible.
            lines += [f"### {folder.name} {path.stem}", ""]
            lines += [f"Configuration `{stamp['config']}`, run on {stamp['run_date']}.", ""]
            lines += ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
            lines += ["| " + " | ".join(row[name] for name in columns) + " |" for row in rows]
            lines += [""]
    (results_dir / "SUMMARY.md").write_text("\n".join(lines + [LIMITS]))
