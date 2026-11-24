"""Raw GOES fire files from the NOAA open data bucket.

FIRMS has no GOES-16 rows for part of the 2024 season. This module fills that gap.
It also reads the live GOES-19 files for the poller.
A raw file holds the full disk. We keep only the fire pixels in the Pantanal box,
with the same mask classes that FIRMS keeps, and save them as one CSV file for each day.
We do not keep the raw files: the gap is approximately 11 GB.

Each raw file also has a mask: one class for each pixel, with or without a fire.
The mask says if the sensor could examine a place. We save the mask of the box for one scan
of each hour. Thus "no detection" can become "examined, no fire" or "not examined".
"""

import csv
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import netCDF4
import numpy as np
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from chispa import config
from chispa.arrival import live_available
from chispa.models import Detection

BUCKET = "https://noaa-goes16.s3.amazonaws.com"
SCAN_START = re.compile(r"<Key>(ABI-L2-FDCF/[^<]*_s(\d{4})(\d{3})(\d{2})(\d{2})[^<]*\.nc)</Key>")
COLUMNS = ["observed_at", "lat", "lon", "mask", "frp_mw"]

# The part of the grid that holds the Pantanal box: rows, then columns. The positions of the full
# grid gave it for a GOES-16 file of 2024-08-15 and for GOES-19 files of 2025-08-15 and
# 2026-11-24: the three are the same. Do not calculate the full grid in a pass: it needs 3 GB.
MASK_WINDOW = (slice(3542, 3898), slice(3481, 3766))

# GOES-19 replaced GOES-16 in 2025. Its bucket gives the time when each file arrived.
LIVE_BUCKET = "https://noaa-goes19.s3.amazonaws.com"
LISTED = re.compile(
    r"<Key>(ABI-L2-FDCF/[^<]*_s(\d{4})(\d{3})(\d{2})(\d{2})[^<]*\.nc)</Key>"
    r"<LastModified>([^<]*)</LastModified>"
)


# The mask classes in groups. The names of the classes are in each raw file (`flag_meanings`).
# A class that is in no group is an error of the input or of the processing: "not_processed".
MASK_GROUPS = {
    "fire": (10, 11, 30, 31),
    "possible_fire": (12, 13, 14, 15, 32, 33, 34, 35),  # FIRMS does not give these classes.
    "no_fire": (100,),  # The sensor examined the pixel and found no fire.
    "cloud": (200, 201, 205, 210, 215, 220, 225, 230, 240, 245),
    "no_background": (170,),  # No background value could be computed for the pixel.
    "water": (150, 151, 152, 153),
    "blocked": (40, 50, 60),  # Off the Earth, a view angle too large, or sun glint.
}


def mask_groups(mask: np.ndarray) -> np.ndarray:
    """Return the group name of each mask class in an array."""
    names = np.full(256, "not_processed", dtype="U13")
    for name, classes in MASK_GROUPS.items():
        names[list(classes)] = name
    return names[mask]


def download_masks(year: int, raw_dir: Path, last: date) -> list[Path]:
    """Save the mask of the Pantanal box for one scan of each hour, as one file for each day.

    A file holds the scan times and one mask for each time. `grid.npz` holds the position of
    each pixel. The grid of one satellite does not change. `last` is the last day to save:
    a day in progress is not complete, and a raw file does not change.
    """
    folder = raw_dir / "goes_mask" / str(year)
    folder.mkdir(parents=True, exist_ok=True)
    paths, day = [], date(year, 1, 1)
    while day <= min(last, date(year, 12, 31)):
        path = folder / f"{day}.npz"
        if not path.exists():
            hourly = {start.hour: (key, start) for key, start in reversed(_list_scans(day))}
            scans = [hourly[hour] for hour in sorted(hourly)]  # The first scan of each hour.
            # The file reader is not safe in threads. Only the downloads run in threads.
            with ThreadPoolExecutor(max_workers=24) as pool:
                urls = [f"{_bucket(day)}/{key}" for key, _ in scans]
                contents = pool.map(lambda url: _get(url).content, urls)
                masks = [_read_mask(content, folder.parent) for content in contents]
            times = np.array([start.isoformat() for _, start in scans])
            np.savez_compressed(path, times=times, mask=np.array(masks, dtype=np.uint8))
        paths.append(path)
        day += timedelta(days=1)
    return paths


def _read_mask(content: bytes, folder: Path) -> np.ndarray:
    with netCDF4.Dataset("scan.nc", memory=content) as dataset:
        rows, columns = MASK_WINDOW
        if not (folder / "grid.npz").exists():
            x, y = np.meshgrid(dataset["x"][columns].filled(), dataset["y"][rows].filled())
            lat, lon = to_lat_lon(x, y, dataset["goes_imager_projection"])
            np.savez_compressed(folder / "grid.npz", lat=lat, lon=lon)
        return dataset["Mask"][rows, columns].filled(0).astype(np.uint8)


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
    rows = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        contents = pool.map(lambda scan: _get(f"{_bucket(day)}/{scan[0]}").content, scans)
        for (_, observed_at), content in zip(scans, contents, strict=True):
            with netCDF4.Dataset("scan.nc", memory=content) as dataset:
                pixels = read_pixels(dataset, MASK_WINDOW)
                rows += [[observed_at.isoformat(), *pixel] for pixel in pixels]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as file:
        csv.writer(file).writerows([COLUMNS, *rows])
    return path


def _in_gap(observed_at: datetime) -> bool:
    return config.GOES_GAP_START <= observed_at < config.GOES_GAP_END


def _bucket(day: date) -> str:
    """Return the bucket of the east satellite of one day."""
    return LIVE_BUCKET if day >= config.GOES19_START.date() else BUCKET


def _list_scans(day: date) -> list[tuple[str, datetime]]:
    """Return (file key, scan start time) for each file of one day, in time sequence."""
    prefix = f"ABI-L2-FDCF/{day.year}/{day.timetuple().tm_yday:03d}/"
    listing = _get(f"{_bucket(day)}/?list-type=2&prefix={prefix}").text
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


def list_live(since: datetime, now: datetime) -> list[tuple[str, datetime, datetime]]:
    """Return the GOES-19 scans with a start from `since` to `now`, in time sequence.

    If a scan has two files, the file that came first stays: a pass cannot wait for a second
    file. Thus a pass after a stop reads the file that a pass with no stop reads.
    """
    scans = {}
    day, last = (
        since.astimezone(UTC).date(),
        now.astimezone(UTC).date(),
    )  # A listing is of a UTC day.
    while day <= last:  # One listing for each day: a day has approximately 144 files.
        prefix = f"ABI-L2-FDCF/{day.year}/{day.timetuple().tm_yday:03d}/"
        for scan in parse_listing(_get(f"{LIVE_BUCKET}/?list-type=2&prefix={prefix}").text):
            first = scans.get(scan[1], scan)
            if since <= scan[1] <= now and scan[2] <= first[2]:
                scans[scan[1]] = scan
        day += timedelta(days=1)
    return [scans[start] for start in sorted(scans)]


def read_live(scans: list[tuple[str, datetime, datetime]]):
    """Give (scan start time, publication time, fire pixels, mask counts, mask) for each scan.

    The mask counts say how many pixels of the Pantanal box each mask group has.
    The mask is the class of each pixel of the mask window, as `download_masks` saves it.
    """
    for key, observed_at, published_at in scans:
        content = _get(f"{LIVE_BUCKET}/{key}").content
        with netCDF4.Dataset("scan.nc", memory=content) as dataset:
            counts = count_mask(dataset, MASK_WINDOW)
            mask = dataset["Mask"][MASK_WINDOW[0], MASK_WINDOW[1]].filled(0).astype(np.uint8)
            yield observed_at, published_at, read_pixels(dataset, MASK_WINDOW), counts, mask


def mask_grid(scan: tuple[str, datetime, datetime]) -> tuple[np.ndarray, np.ndarray]:
    """Return the latitude and the longitude of each pixel of the mask window, from a live scan."""
    with netCDF4.Dataset("scan.nc", memory=_get(f"{LIVE_BUCKET}/{scan[0]}").content) as dataset:
        rows, columns = MASK_WINDOW
        x, y = np.meshgrid(dataset["x"][columns].filled(), dataset["y"][rows].filled())
        return to_lat_lon(x, y, dataset["goes_imager_projection"])


def count_mask(dataset: netCDF4.Dataset, window: tuple[slice, slice]) -> dict[str, int]:
    """Return the number of pixels of the Pantanal box in each mask group."""
    rows, columns = window
    x, y = np.meshgrid(dataset["x"][columns].filled(), dataset["y"][rows].filled())
    lat, lon = to_lat_lon(x, y, dataset["goes_imager_projection"])
    groups = mask_groups(dataset["Mask"][rows, columns].filled(0))[_in_box(lat, lon)]
    return {name: int((groups == name).sum()) for name in (*MASK_GROUPS, "not_processed")}


def _get(url: str) -> requests.Response:
    """Get one URL. A connection that drops is tried again: a year of scans is many requests."""
    with requests.Session() as session:
        session.mount("https://", HTTPAdapter(max_retries=Retry(total=5, backoff_factor=2)))
        answer = session.get(url, timeout=180)
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


def parse_file(path: Path, platform: str) -> list[Detection]:
    """Return the detections of one day file. The platform is GOES16 or GOES19."""
    with path.open(newline="") as file:
        return [_parse_row(row, platform) for row in csv.DictReader(file)]


def _parse_row(row: dict, platform: str) -> Detection:
    observed_at = datetime.fromisoformat(row["observed_at"])
    # A live row has the time when we first saw it. A recorded row has only an estimate.
    available_at, estimated = observed_at + config.AVAILABLE_DELAY["abi"], True
    if row.get("first_seen_at"):
        available_at, estimated = live_available(
            datetime.fromisoformat(row["first_seen_at"]),
            datetime.fromisoformat(row["published_at"]),
        )
    return Detection(
        source="noaa",
        sensor_family="abi",
        platform=platform,
        observed_at=observed_at,
        available_at=available_at,
        lat=float(row["lat"]),
        lon=float(row["lon"]),
        footprint_m=config.GOES_FOOTPRINT_M,
        frp_mw=float(row["frp_mw"]) if row["frp_mw"] else None,
        source_confidence=config.GOES_CONFIDENCE[int(row["mask"])],
        available_estimated=estimated,
    )
