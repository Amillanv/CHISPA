"""The records that all modules share.

Each source has its own file format.
One common record lets the fusion read all sources in the same way.
"""

from dataclasses import dataclass
from datetime import datetime

SENSOR_FAMILIES = ("viirs", "modis", "abi", "avhrr", "camera", "person")
SOURCE_CONFIDENCES = ("low", "nominal", "high")


@dataclass(frozen=True)
class Detection:
    """One observation of a possible fire from one sensor at one time."""

    source: str
    sensor_family: str
    platform: str
    observed_at: datetime
    available_at: datetime
    lat: float
    lon: float
    footprint_m: float
    frp_mw: float | None
    source_confidence: str

    def __post_init__(self) -> None:
        """Reject a record that breaks the data conventions."""
        if self.sensor_family not in SENSOR_FAMILIES:
            raise ValueError(f"Unknown sensor family: {self.sensor_family!r}.")
        if self.source_confidence not in SOURCE_CONFIDENCES:
            raise ValueError(f"Unknown source confidence: {self.source_confidence!r}.")
        if not -90 <= self.lat <= 90 or not -180 <= self.lon <= 180:
            raise ValueError(f"Position is not on the Earth: {self.lat}, {self.lon}.")
        if self.footprint_m <= 0:
            raise ValueError(f"Footprint must be more than zero: {self.footprint_m}.")
        for name in ("observed_at", "available_at"):
            if getattr(self, name).utcoffset() is None:
                raise ValueError(f"{name} has no timezone. Use a UTC time.")
        if self.available_at < self.observed_at:
            raise ValueError("available_at is before observed_at.")
