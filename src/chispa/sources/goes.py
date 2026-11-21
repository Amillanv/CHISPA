"""Raw GOES fire files from the NOAA open data bucket.

FIRMS has no GOES-16 rows for part of the 2024 season. This module fills that gap.
It also reads the live GOES-19 files for the poller.
A raw file holds the full disk. We keep only the fire pixels in the Pantanal box,
with the same mask classes that FIRMS keeps, and save them as one CSV file for each day.
We do not keep the raw files: the gap is approximately 11 GB.
"""

import csv
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import netCDF4
import numpy as np
import requests

from chispa import config
from chispa.models import Detection

BUCKET = "https://noaa-goes16.s3.amazonaws.com"
SCAN_START = re.compile(r"<Key>(ABI-L2-FDCF/[^<]*_s(\d{4})(\d{3})(\d{2})(\d{2})[^<]*\.nc)</Key>")
COLUMNS = ["observed_at", "lat", "lon", "mask", "frp_mw"]

# GOES-19 replaced GOES-16 in 2025. Its bucket gives the time when each file arrived.
LIVE_BUCKET = "https://noaa-goes19.s3.amazonaws.com"
LISTED = re.compile(
    r"<Key>(ABI-L2-FDCF/[^<]*_s(\d{4})(\d{3})(\d{2})(\d{2})[^<]*\.nc)</Key>"
    r"<LastModified>([^<]*)</LastModified>"
)


def download_gap(raw_dir: Path) -> list[Path]:
    """Save one CSV file of fire pixels for each day of the gap and return the paths."""
    paths = []
    day = config.GOES_GAP_START.date()
    while day <= config.GOES_GAP_END.date():
        paths.append(_download_day(day, raw_dir))
        day += timedelta(days=1)
    return paths


def _download_day(day: date, raw_dir: Path) -> Path:
    path = raw_dir / "goes" / f"{day}.csv"
    if path.exists():
        return path
    scans = [scan for scan in _list_scans(day) if _in_gap(scan[1])]
    rows, window = [], None
    with ThreadPoolExecutor(max_workers=8) as pool:
        contents = pool.map(lambda scan: _get(f"{BUCKET}/{scan[0]}").content, scans)
        for (_, observed_at), content in zip(scans, contents, strict=True):
            with netCDF4.Dataset("scan.nc", memory=content) as dataset:
                window = window or find_window(dataset)
                rows += [
                    [observed_at.isoformat(), *pixel] for pixel in read_pixels(dataset, window)
                ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as file:
        csv.writer(file).writerows([COLUMNS, *rows])
    return path


def _in_gap(observed_at: datetime) -> bool:
    return config.GOES_GAP_START <= observed_at < config.GOES_GAP_END


def _list_scans(day: date) -> list[tuple[str, datetime]]:
    """Return (file key, scan start time) for each file of one day, in time sequence."""
    prefix = f"ABI-L2-FDCF/{day.year}/{day.timetuple().tm_yday:03d}/"
    listing = _get(f"{BUCKET}/?list-type=2&prefix={prefix}").text
    scans = {}
    # Some scans have two files. The keys sort by creation time, thus the newest file wins.
    for key, year, day_of_year, hour, minute in sorted(SCAN_START.findall(listing)):
        start = datetime(int(year), 1, 1, int(hour), int(minute), tzinfo=UTC)
        scans[start + timedelta(days=int(day_of_year) - 1)] = key
    return [(key, start) for start, key in sorted(scans.items())]


def parse_listing(listing: str) -> list[tuple[str, datetime, datetime]]:
    """Return (file key, scan start time, publication time) for each file in a bucket listing."""
    scans = []
    for key, year, day_of_year, hour, minute, modified in LISTED.findall(listing):
        start = datetime(int(year), 1, 1, int(hour), int(minute), tzinfo=UTC)
        published_at = datetime.fromisoformat(modified.replace("Z", "+00:00"))
        scans.append((key, start + timedelta(days=int(day_of_year) - 1), published_at))
    return scans


def list_live(now: datetime) -> list[tuple[str, datetime, datetime]]:
    """Return the GOES-19 scans of the last hours, in time sequence. `config.py` gives how many."""
    scans = {}
    for back in range(int(config.LIVE_GOES_LOOKBACK / timedelta(hours=1)), -1, -1):
        hour = now - timedelta(hours=back)
        prefix = f"ABI-L2-FDCF/{hour.year}/{hour.timetuple().tm_yday:03d}/{hour.hour:02d}/"
        for scan in parse_listing(_get(f"{LIVE_BUCKET}/?list-type=2&prefix={prefix}").text):
            scans.setdefault(scan[1], scan)  # If a scan has two files, the first file stays.
    return [scans[start] for start in sorted(scans)]


def read_live(scans: list[tuple[str, datetime, datetime]]):
    """Give (scan start time, publication time, fire pixels) for each scan."""
    window = None
    for key, observed_at, published_at in scans:
        content = _get(f"{LIVE_BUCKET}/{key}").content
        with netCDF4.Dataset("scan.nc", memory=content) as dataset:
            window = window or find_window(dataset)
            yield observed_at, published_at, read_pixels(dataset, window)


def _get(url: str) -> requests.Response:
    answer = requests.get(url, timeout=180)
    answer.raise_for_status()
    return answer


def to_lat_lon(x: np.ndarray, y: np.ndarray, projection) -> tuple[np.ndarray, np.ndarray]:
    """Convert GOES scan angles in radians to latitude and longitude in degrees.

    The formula is from the GOES-R Product User Guide. A point off the Earth gives NaN.
    """
    a, b = projection.semi_major_axis, projection.semi_minor_axis
    h = projection.perspective_point_height + a
    lon_0 = np.deg2rad(projection.longitude_of_projection_origin)
    with np.errstate(invalid="ignore"):
        p = np.sin(x) ** 2 + np.cos(x) ** 2 * (np.cos(y) ** 2 + (a / b) ** 2 * np.sin(y) ** 2)
        q = -2 * h * np.cos(x) * np.cos(y)
        distance = (-q - np.sqrt(q**2 - 4 * p * (h**2 - a**2))) / (2 * p)
        sx = distance * np.cos(x) * np.cos(y)
        sy = -distance * np.sin(x)
        sz = distance * np.cos(x) * np.sin(y)
        lat = np.arctan((a / b) ** 2 * sz / np.sqrt((h - sx) ** 2 + sy**2))
        lon = lon_0 - np.arctan(sy / (h - sx))
    return np.rad2deg(lat), np.rad2deg(lon)


def find_window(dataset: netCDF4.Dataset) -> tuple[slice, slice]:
    """Return the (rows, columns) part of the grid that contains the Pantanal box.

    The grid is the same in each file. Thus we find the window one time for each day.
    """
    x, y = np.meshgrid(dataset["x"][:].filled(), dataset["y"][:].filled())
    lat, lon = to_lat_lon(x, y, dataset["goes_imager_projection"])
    rows, columns = np.where(_in_box(lat, lon))
    return slice(rows.min(), rows.max() + 1), slice(columns.min(), columns.max() + 1)


def _in_box(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    west, south, east, north = config.PANTANAL_BOX
    return (lat >= south) & (lat <= north) & (lon >= west) & (lon <= east)


def read_pixels(dataset: netCDF4.Dataset, window: tuple[slice, slice]) -> list[list]:
    """Return [lat, lon, mask, frp_mw] for each fire pixel in the Pantanal box."""
    rows, columns = window
    mask = dataset["Mask"][rows, columns].filled(0)
    power = dataset["Power"][rows, columns].filled(np.nan)
    x, y = np.meshgrid(dataset["x"][columns].filled(), dataset["y"][rows].filled())
    lat, lon = to_lat_lon(x, y, dataset["goes_imager_projection"])
    keep = np.isin(mask, list(config.GOES_CONFIDENCE)) & _in_box(lat, lon)
    return [
        [round(float(lat[i]), 6), round(float(lon[i]), 6), int(mask[i]), _number(power[i])]
        for i in zip(*np.where(keep), strict=True)
    ]


def _number(value: float) -> float | str:
    return "" if np.isnan(value) else round(float(value), 4)


def parse_file(path: Path) -> list[Detection]:
    """Return the detections of one day file."""
    with path.open(newline="") as file:
        return [_parse_row(row) for row in csv.DictReader(file)]


def _parse_row(row: dict) -> Detection:
    observed_at = datetime.fromisoformat(row["observed_at"])
    return Detection(
        source="noaa",
        sensor_family="abi",
        platform="GOES16",
        observed_at=observed_at,
        available_at=observed_at + config.AVAILABLE_DELAY["abi"],
        lat=float(row["lat"]),
        lon=float(row["lon"]),
        footprint_m=config.GOES_FOOTPRINT_M,
        frp_mw=float(row["frp_mw"]) if row["frp_mw"] else None,
        source_confidence=config.GOES_CONFIDENCE[int(row["mask"])],
    )
