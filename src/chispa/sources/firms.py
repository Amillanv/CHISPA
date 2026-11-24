"""NASA FIRMS: hotspots from VIIRS, MODIS and GOES as CSV files.

FIRMS gives three sensor families in one format, thus one module reads all three.
The download and the parse are separate steps. A raw file on disk is never requested again.
"""

import csv
import io
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import requests

from chispa import config
from chispa.models import Detection

API = "https://firms.modaps.eosdis.nasa.gov"
HEADER_START = "latitude,longitude"

# Product name -> sensor family. We use the archive products for the polar-orbit sensors.
PRODUCTS = {
    "VIIRS_SNPP_SP": "viirs",
    "VIIRS_NOAA20_SP": "viirs",
    "VIIRS_NOAA21_SP": "viirs",
    "MODIS_SP": "modis",
    "GOES_NRT": "abi",
}
# The live products. Suomi NPP has no live product: its data stopped on 2026-11-02.
# We do not use the live GOES product of FIRMS: the raw GOES files are quicker.
LIVE_PRODUCTS = {"VIIRS_NOAA20_NRT": "viirs", "VIIRS_NOAA21_NRT": "viirs", "MODIS_NRT": "modis"}
# FIRMS makes an archive product some months after the observation. For the days that have
# no archive product, the year in progress uses the live product of the same satellite.
LATE_PRODUCTS = {
    "VIIRS_SNPP_SP": "VIIRS_SNPP_NRT",
    "VIIRS_NOAA20_SP": "VIIRS_NOAA20_NRT",
    "VIIRS_NOAA21_SP": "VIIRS_NOAA21_NRT",
    "MODIS_SP": "MODIS_NRT",
}
FAMILIES = PRODUCTS | LIVE_PRODUCTS | {"VIIRS_SNPP_NRT": "viirs"}
# A pass asks for the maximum of 5 days. Thus a stop of the poller of less than 4 days loses
# no row. A request for 2 days lost a row of 2026-11-21 in a stop of 28 hours.
LIVE_DAYS = 5
# The maximum number of days that the API gives in one request.
MAX_DAYS = {"viirs": 5, "modis": 5, "abi": 2}
# The `satellite` field -> our platform name. We ignore rows with other values:
# `G16FRP` and `G19FRP` have no documentation that we know. `Met10` and `Met12` see the Pantanal
# at a bad angle. FIRMS gives `G19` in place of `G16` from April 2025.
PLATFORMS = {
    "N": "SNPP",
    "N20": "NOAA20",
    "N21": "NOAA21",
    "Terra": "TERRA",
    "Aqua": "AQUA",
    "G16": "GOES16",
    "G19": "GOES19",
}
VIIRS_CONFIDENCE = {"l": "low", "n": "nominal", "h": "high"}


def key_status(key: str) -> dict:
    """Return the transaction count and limit of the key. A bad key raises an error."""
    answer = _get(f"{API}/mapserver/mapkey_status/?MAP_KEY={key}", "key status")
    return answer.json()


def download_year(year: int, key: str, raw_dir: Path) -> list[tuple[str, Path]]:
    """Save all raw files of one year and return (product, path) for each file.

    The year of the live logs stops on the day before the first live log. For its days with
    no archive product, we get the live product of the same satellite.
    """
    last = min(date(year, 12, 31), config.LIVE_START.date() - timedelta(days=1))
    ends = archive_ends(key) if year == config.LIVE_START.year else {}
    files = []
    for product in PRODUCTS:
        archive_last = min(ends.get(product, last), last)
        start = date(year, 1, 1)
        while start <= last:
            in_archive = start <= archive_last or product not in LATE_PRODUCTS
            name = product if in_archive else LATE_PRODUCTS[product]
            limit = archive_last if in_archive and product in LATE_PRODUCTS else last
            days = min(MAX_DAYS[PRODUCTS[product]], (limit - start).days + 1)
            files.append((name, _download(name, start, days, key, raw_dir)))
            start += timedelta(days=days)
    return files


def archive_ends(key: str) -> dict[str, date]:
    """Return the last day that each product has data, as FIRMS says."""
    text = _get(f"{API}/api/data_availability/csv/{key}/ALL", "data availability").text
    rows = [line.split(",") for line in text.splitlines()[1:]]
    return {row[0]: date.fromisoformat(row[2]) for row in rows if len(row) == 3}


def _download(product: str, start: date, days: int, key: str, raw_dir: Path) -> Path:
    path = raw_dir / "firms" / product / f"{start}_{days}d.csv"
    if path.exists():
        return path
    box = ",".join(str(value) for value in config.PANTANAL_BOX)
    url = f"{API}/api/area/csv/{key}/{product}/{box}/{days}/{start}"
    text = _get(url, f"{product} {start}").text
    if not text.startswith(HEADER_START):
        raise RuntimeError(f"FIRMS gave no CSV for {product} {start}: {text[:200]!r}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    time.sleep(config.FIRMS_PAUSE_S)
    return path


def download_live(product: str, key: str) -> list[dict]:
    """Return the rows of the last days of one live product, with the fields that FIRMS gives."""
    box = ",".join(str(value) for value in config.PANTANAL_BOX)
    text = _get(f"{API}/api/area/csv/{key}/{product}/{box}/{LIVE_DAYS}", product).text
    if not text.startswith(HEADER_START):
        raise RuntimeError(f"FIRMS gave no CSV for {product}: {text[:200]!r}")
    return list(csv.DictReader(io.StringIO(text)))


def _get(url: str, label: str) -> requests.Response:
    # The address contains the key. We catch the error to keep the key out of the message.
    try:
        answer = requests.get(url, timeout=180)
    except requests.RequestException as error:
        raise RuntimeError(f"FIRMS request failed ({label}): {type(error).__name__}") from None
    if answer.status_code != 200:
        raise RuntimeError(
            f"FIRMS request failed ({label}): HTTP {answer.status_code} {answer.text[:200]!r}"
        )
    return answer


def parse_file(path: Path, product: str) -> tuple[list[Detection], int]:
    """Return the detections of one raw file and the number of rejected rows."""
    detections, rejected = [], 0
    with path.open(newline="") as file:
        for row in csv.DictReader(file):
            if row["satellite"] not in PLATFORMS:
                continue
            try:
                detections.append(parse_row(row, FAMILIES[product]))
            except (ValueError, KeyError):
                rejected += 1
    return detections, rejected


def parse_row(row: dict, sensor_family: str) -> Detection:
    """Make one detection from one CSV row. A bad row raises ValueError or KeyError."""
    day = date.fromisoformat(row["acq_date"])
    clock = row["acq_time"].zfill(4)  # `513` is 05:13 UTC.
    observed_at = datetime(day.year, day.month, day.day, int(clock[:2]), int(clock[2:]), tzinfo=UTC)
    frp_mw = float(row["frp"])
    # A live row has the time when we first saw it. A recorded row has only an estimate.
    seen = row.get("first_seen_at")
    return Detection(
        source="firms",
        sensor_family=sensor_family,
        platform=PLATFORMS[row["satellite"]],
        observed_at=observed_at,
        available_at=datetime.fromisoformat(seen)
        if seen
        else observed_at + config.AVAILABLE_DELAY[sensor_family],
        lat=float(row["latitude"]),
        lon=float(row["longitude"]),
        footprint_m=_footprint_m(row, sensor_family),
        frp_mw=frp_mw if frp_mw >= 0 else None,  # FIRMS writes -999 for "no value".
        source_confidence=_confidence(row["confidence"], sensor_family),
        available_estimated=not seen,
    )


def _footprint_m(row: dict, sensor_family: str) -> float:
    if sensor_family == "abi":
        return config.GOES_FOOTPRINT_M
    # `scan` and `track` are the pixel size in kilometres. The radius is half the larger side.
    return max(float(row["scan"]), float(row["track"])) * 1000 / 2


def _confidence(value: str, sensor_family: str) -> str:
    if sensor_family == "viirs":
        return VIIRS_CONFIDENCE[value]
    if sensor_family == "abi":
        return config.GOES_CONFIDENCE[int(float(value))]
    percent = float(value)
    if percent >= config.MODIS_HIGH_FROM:
        return "high"
    return "nominal" if percent >= config.MODIS_NOMINAL_FROM else "low"
