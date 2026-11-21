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
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

from chispa import config
from chispa.models import Detection

FOLDER = "https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/mensal/Brasil/"
# One file for each 10 minutes, for all of South America. The server keeps some days of files.
LIVE_FOLDER = "https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/10min/"

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
    "GOES-19": ("abi", "GOES19"),
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


def list_live(now: datetime) -> list[str]:
    """Return the names of the files of 10 minutes of the last hours. `config.py` gives how many."""
    listing = requests.get(LIVE_FOLDER, timeout=60)
    listing.raise_for_status()
    names = sorted(set(re.findall(r"focos_10min_\d{8}_\d{4}\.csv", listing.text)))
    return [name for name in names if now - config.LIVE_LOOKBACK <= live_time(name) <= now]


def live_time(name: str) -> datetime:
    """Return the time in the name of a file of 10 minutes."""
    return datetime.strptime(name, "focos_10min_%Y%m%d_%H%M.csv").replace(tzinfo=UTC)


def read_live(name: str) -> tuple[datetime, list[dict]]:
    """Return the publication time of one file of 10 minutes, and its rows in the Pantanal box."""
    answer = requests.get(LIVE_FOLDER + name, timeout=60)
    answer.raise_for_status()
    published_at = parsedate_to_datetime(answer.headers["Last-Modified"])
    rows = csv.DictReader(io.StringIO(answer.text))
    return published_at, [row for row in rows if _in_box(float(row["lat"]), float(row["lon"]))]


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
    # A monthly file has the field `data_hora_gmt`. A file of 10 minutes has the field `data`.
    observed_at = datetime.fromisoformat(row.get("data_hora_gmt") or row["data"]).replace(
        tzinfo=UTC
    )
    # A live row has the time when we first saw it. A recorded row has only an estimate.
    seen = row.get("first_seen_at")
    return Detection(
        source="inpe",
        sensor_family=sensor_family,
        platform=platform,
        observed_at=observed_at,
        available_at=datetime.fromisoformat(seen)
        if seen
        else observed_at + config.AVAILABLE_DELAY[sensor_family],
        lat=float(row["lat"]),
        lon=float(row["lon"]),
        footprint_m=config.INPE_FOOTPRINT_M[sensor_family],
        frp_mw=float(row["frp"]) if row.get("frp") else None,  # Some rows have no value.
        source_confidence="nominal",  # INPE gives no confidence value.
    )
