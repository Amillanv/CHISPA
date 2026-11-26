"""The level of the Paraguay River at Ladário for each day, from the water agency of Brazil (ANA).

The flood of the Pantanal changes with the year, and the river level at Ladário is its usual
measure. The growth risk examines it as an input for the state of the region.
"""

from datetime import UTC, date, datetime
from pathlib import Path
from xml.etree import ElementTree

import requests

URL = "http://telemetriaws1.ana.gov.br/ServiceANA.asmx/HidroSerieHistorica"
STATION = "66825000"  # Ladário, on the Paraguay River.
LEVELS = "1"  # The type of data in a request: river levels.


def download_year(year: int, raw_dir: Path) -> list[Path]:
    """Save the answer of ANA for one year and return the path.

    ANA adds the months of a year with a delay. Thus a year that is not complete is read again.
    """
    path = raw_dir / "river" / f"{year}.xml"
    if not path.exists() or year >= datetime.now(UTC).year:
        days = {"dataInicio": f"01/01/{year}", "dataFim": f"31/12/{year}"}
        query = {"codEstacao": STATION, "tipoDados": LEVELS, "nivelConsistencia": ""} | days
        answer = requests.get(URL, params=query, timeout=120)
        answer.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(answer.content)
    return [path]


def parse_file(path: Path) -> dict[date, float]:
    """Return the level of each day of one file that has a value, in metres.

    The answer has one or more rows for a month, each with one field for each day, in
    centimetres. The rows of a month can have different marks of the check by ANA. We use the
    row with the most days, and the row with the larger mark if two rows have the same number.
    """
    best: dict[str, tuple[int, int, list[float | None]]] = {}
    for row in ElementTree.parse(path).iter("SerieHistorica"):
        month = row.findtext("DataHora")[:7]
        days = [row.findtext(f"Cota{day:02d}") for day in range(1, 32)]
        values = [None if text in (None, "") else float(text) / 100 for text in days]
        found = (sum(value is not None for value in values), int(row.findtext("NivelConsistencia")))
        if found > best.get(month, (0, 0))[:2]:
            best[month] = (*found, values)
    levels = {}
    for month, (_, _, values) in best.items():
        year, number = int(month[:4]), int(month[5:])
        levels |= {
            date(year, number, day): value
            for day, value in enumerate(values, 1)
            if value is not None
        }
    return levels


def read_days(raw_dir: Path, first_year: int, last_year: int) -> dict[date, float]:
    """Return the level of each day with a value, in metres, for the years from first to last."""
    levels: dict[date, float] = {}
    for year in range(first_year, last_year + 1):
        path = raw_dir / "river" / f"{year}.xml"
        if not path.exists():
            raise RuntimeError(f"Run `chispa fetch river --year {year}` first.")
        levels |= parse_file(path)
    return levels
