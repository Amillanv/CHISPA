"""Write the result tables as CSV files and as one summary document.

Code makes each number in the summary. A person does not edit the summary by hand.
"""

import csv
import hashlib
from datetime import UTC, datetime
from pathlib import Path

from chispa import config

LIMITS = """Limits of these results:

- The sources are satellites only. There are no camera detections or community reports.
- The burn scar map gives the month of an image, not the day of a fire.
  Thus a delay is relative to the first detection from all sources, not to the start of the fire.
- An unmatched detection is not always a false alarm. The fire can be too small for the map.
- GOES has no low-probability detections, and has holes in late September to November 2024.
- The availability delay of each sensor family is an estimate in `config.py`.
- Smoke level is not in these tables yet.
- A scar in January can have detections in December of the year before. We do not count those.
"""


def config_hash() -> str:
    """Return a short hash of `config.py`. Two runs with the same hash used the same settings."""
    return hashlib.sha256(Path(config.__file__).read_bytes()).hexdigest()[:12]


def write_tables(tables: dict[str, list[dict]], year: int, results_dir: Path) -> None:
    """Save each table of one year as a CSV file, with the configuration hash in each row."""
    folder = results_dir / str(year)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = {"config": config_hash(), "run_date": datetime.now(UTC).date().isoformat()}
    for name, rows in tables.items():
        with (folder / f"{name}.csv").open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=[*rows[0], *stamp])
            writer.writeheader()
            writer.writerows({**row, **stamp} for row in rows)


def write_summary(results_dir: Path) -> None:
    """Make `SUMMARY.md` again from all the CSV files in the results folder."""
    lines = ["# Results", "", "Code makes this file. Do not edit it by hand.", ""]
    for folder in sorted(path for path in results_dir.iterdir() if path.is_dir()):
        role = "test year" if folder.name == str(config.TEST_YEAR) else "development year"
        lines += [f"## {folder.name} ({role})", ""]
        for path in sorted(folder.glob("*.csv")):
            with path.open(newline="") as file:
                rows = list(csv.DictReader(file))
            columns = [name for name in rows[0] if name not in ("config", "run_date")]
            lines += [f"### {path.stem}", ""]
            lines += [f"Configuration `{rows[0]['config']}`, run on {rows[0]['run_date']}.", ""]
            lines += ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
            lines += ["| " + " | ".join(row[name] for name in columns) + " |" for row in rows]
            lines += [""]
    (results_dir / "SUMMARY.md").write_text("\n".join(lines + [LIMITS]))
