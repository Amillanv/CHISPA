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


@dataclass(frozen=True)
class Scar:
    """A connected area that MapBiomas Fogo maps as burned in one month.

    `number` identifies the scar in its year. The scar grid of that year holds this number
    in each pixel of the scar. The position is the mean of the pixel centres.
    """

    year: int
    number: int
    month: int
    area_ha: float
    lat: float
    lon: float
    south: float
    west: float
    north: float
    east: float
    first_burn_day: int | None = None  # day of the year, from the burn day product
    last_burn_day: int | None = None


@dataclass(frozen=True)
class Event:
    """A group of detections that the fusion assigns to one fire."""

    id: int
    first_observed_at: datetime
    last_observed_at: datetime
    first_available_at: datetime
    detections: int
    lat: float
    lon: float
    south: float
    west: float
    north: float
    east: float
    max_frp_mw: float | None
    level: str
    families: str
    passes: int


@dataclass(frozen=True)
class Alert:
    """One state of the alert of an event: the confidence level from a given time.

    An event has one alert. Each record is a change of that alert, with its evidence.
    """

    event_id: int
    at: datetime
    level: str
    families: str
    passes: int
