"""INPE Queimadas: the Brazilian hotspot database as monthly CSV files.

INPE reads many of the same satellites as FIRMS with its own methods.
It also gives the AVHRR sensors, which FIRMS does not give.
A monthly file is for all of Brazil. We keep the raw file and read only the Pantanal box.
"""

import csv
import io
import re
import zipfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import requests

from chispa import config
from chispa.models import Detection

FOLDER = "https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/mensal/Brasil/"

# The `satelite` field -> (sensor family, platform). We ignore `MSG-03`:
# it is a Meteosat satellite that sees the Pantanal at a bad angle.
SATELLITES = {
    "NOAA-20": ("viirs", "NOAA20"),
    "NOAA-21": ("viirs", "NOAA21"),
    "NPP-375": ("viirs", "SNPP"),
    "NPP-375D": ("viirs", "SNPP"),
    "AQUA_M-T": ("modis", "AQUA"),
    "AQUA_M-M": ("modis", "AQUA"),
    "TERRA_M-T": ("modis", "TERRA"),
    "TERRA_M-M": ("modis", "TERRA"),
    "GOES-16": ("abi", "GOES16"),
    "METOP-B": ("avhrr", "METOPB"),
    "METOP-C": ("avhrr", "METOPC"),
    "NOAA-18": ("avhrr", "NOAA18"),
    "NOAA-18D": ("avhrr", "NOAA18"),
    "NOAA-19": ("avhrr", "NOAA19"),
    "NOAA-19D": ("avhrr", "NOAA19"),
}


def download_year(year: int, raw_dir: Path) -> list[Path]:
    """Save the twelve monthly files of one year and return the paths."""
    listing = requests.get(FOLDER, timeout=60)
    listing.raise_for_status()
    names = sorted(set(re.findall(rf"focos_mensal_br_{year}\d\d\.(?:csv|zip)", listing.text)))
    if len(names) != 12:
        raise RuntimeError(f"INPE lists {len(names)} monthly files for {year}, not 12.")
    return [_download(name, raw_dir) for name in names]


def _download(name: str, raw_dir: Path) -> Path:
    path = raw_dir / "inpe" / name
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(".part")
    # The server is slow. We write to a temporary name, thus a stopped download is not kept.
    with requests.get(FOLDER + name, stream=True, timeout=(30, 300)) as answer:
        answer.raise_for_status()
        with part.open("wb") as file:
            for chunk in answer.iter_content(chunk_size=1 << 20):
                file.write(chunk)
        expected = int(answer.headers.get("Content-Length", part.stat().st_size))
    if part.stat().st_size != expected:
        raise RuntimeError(f"INPE file {name} is not complete. Run the command again.")
    part.rename(path)
    return path


def parse_file(path: Path) -> tuple[list[Detection], int, Counter]:
    """Return the detections in the Pantanal box, the number of rejected rows,
    and a count of the rows in the box from satellites that we do not use."""
    detections, rejected, unused = [], 0, Counter()
    with _open_text(path) as file:
        for row in csv.DictReader(file):
            try:
                if not _in_box(float(row["lat"]), float(row["lon"])):
                    continue
                if row["satelite"] not in SATELLITES:
                    unused[row["satelite"]] += 1
                    continue
                detections.append(parse_row(row))
            except (ValueError, KeyError, TypeError):
                rejected += 1
    return detections, rejected, unused


def _open_text(path: Path) -> io.TextIOBase:
    if path.suffix != ".zip":
        return path.open(newline="", encoding="utf-8")
    archive = zipfile.ZipFile(path)
    return io.TextIOWrapper(archive.open(archive.namelist()[0]), newline="", encoding="utf-8")


def _in_box(lat: float, lon: float) -> bool:
    west, south, east, north = config.PANTANAL_BOX
    return south <= lat <= north and west <= lon <= east


def parse_row(row: dict) -> Detection:
    """Make one detection from one CSV row. A bad row raises an error."""
    sensor_family, platform = SATELLITES[row["satelite"]]
    observed_at = datetime.fromisoformat(row["data_hora_gmt"]).replace(tzinfo=UTC)
    return Detection(
        source="inpe",
        sensor_family=sensor_family,
        platform=platform,
        observed_at=observed_at,
        available_at=observed_at + config.AVAILABLE_DELAY[sensor_family],
        lat=float(row["lat"]),
        lon=float(row["lon"]),
        footprint_m=config.INPE_FOOTPRINT_M[sensor_family],
        frp_mw=float(row["frp"]) if row.get("frp") else None,  # Some rows have no value.
        source_confidence="nominal",  # INPE gives no confidence value.
    )
