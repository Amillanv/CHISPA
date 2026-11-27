"""The inputs of a front for the growth forecast: what we know at the time of its look.

A forecast for a front can use only the past: the pixels of its look and of the looks before,
the maps that existed at the look, and the weather to the time of the look. This module makes
those inputs for each front of a look. An input for a sector has a name that ends with `_s`.
`docs/method.md` section 11.28 gives the list and the reason of each group, and section 11.31
gives the maps that a look can have.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from chispa import config, fronts
from chispa.evaluation.fronts import is_day_look
from chispa.grid import layer_grid
from chispa.sources import burned, landcover, weather

ON_FRONT = ("forest", "savanna", "wetland", "grassland", "pasture")
AHEAD = ("water", "forest", "savanna", "wetland", "grassland", "pasture")
# The inputs from the annual map of the burned ground of the year before.
LAST_YEAR = ("burned_last_year", "ahead_burned_last_year_s")


@dataclass(frozen=True)
class Layers:
    """The maps and the weather for the fronts of one year.

    `cover` has the number of the land cover group of each layer cell, from the year before.
    `burned` has the burned share of the year before, and the largest of the two years before it.
    `days` and `wind` start at `first_day`: the daily measures and the wind of each block.
    """

    cover: np.ndarray
    burned: tuple[np.ndarray, np.ndarray]
    first_day: date
    days: dict[str, np.ndarray]
    wind: np.ndarray


def load_layers(raw_dir: Path, year: int, live: bool = False) -> Layers:
    """Return the layers of one year, as a look of that year can have them.

    The land cover is the map of some years before (`config.py`), or of the last year that
    the map has if that is older. The burned map of the year before must be on disk: thus two
    computers make the same trees. `live`: for a live forecast that map can be absent, and
    then it has no value. The weather starts in December of the year before. It ends with the
    last complete month on disk, or with the last complete day of a month in progress.
    """
    to_group = np.zeros(256, dtype=int)
    for number, name in enumerate(config.COVER_GROUPS, start=1):
        to_group[list(config.COVER_GROUPS[name])] = number
    cover_year = min(year - config.FRONT_COVER_YEARS_BEFORE, config.LANDCOVER_LAST_YEAR)
    cover = to_group[landcover.read_year(cover_year, raw_dir)]
    before = np.maximum(burned.read_year(year - 2, raw_dir), burned.read_year(year - 3, raw_dir))
    last = np.full(before.shape, np.nan, dtype=np.float32)
    if not live or (raw_dir / "burned" / f"{year - 1}.npz").exists():
        last = burned.read_year(year - 1, raw_dir)  # If absent, this stops with an instruction.
    first = date(year - 1, 12, 1)
    days, wind = weather.read_newest(raw_dir, first, date(year + 1, 1, 31))
    return Layers(cover, (last, before), first, days, wind)


def units() -> np.ndarray:
    """Return the direction of the centre of each sector as (north, east)."""
    angles = np.deg2rad(np.arange(config.FRONT_SECTORS) * 360 / config.FRONT_SECTORS)
    return np.column_stack([np.cos(angles), np.sin(angles)])


def _by_sector(owner: np.ndarray, lines: np.ndarray, count: int) -> np.ndarray:
    sectors = config.FRONT_SECTORS
    index = owner * sectors + fronts.sector(lines)
    return np.bincount(index, minlength=count * sectors).reshape(count, sectors).astype(float)


def shape_inputs(look: fronts.Look, power: np.ndarray) -> tuple[dict, np.ndarray, np.ndarray]:
    """Return the inputs of the size, the fire power and the shape of each front, with the centre
    of each front and its reach from the centre to each sector, in metres.

    A pixel with no fire power is not a pixel with a power of 0: the power inputs of a front come
    from its pixels with a value. A front with no such pixel has no value for them.
    """
    labels, count = look.labels, look.labels.max() + 1
    size = np.bincount(labels, minlength=count)
    known = ~np.isnan(power)
    power = np.where(known, power, 0.0)
    measured, total = (np.bincount(labels, values, minlength=count) for values in (known, power))
    largest, none = np.zeros(count), measured == 0
    np.maximum.at(largest, labels, power)
    centre = (
        np.column_stack([np.bincount(labels, look.points[:, i]) for i in (0, 1)]) / size[:, None]
    )
    offset = look.points - centre[labels]
    reach = np.zeros((count, config.FRONT_SECTORS))
    np.maximum.at(reach, labels, offset @ units().T)
    hot = np.column_stack([np.bincount(labels, offset[:, i] * power) for i in (0, 1)])
    # Where the fire power is, from the centre of the front: the hot side of a front.
    heat = (hot / np.maximum(total, 1e-9)[:, None]) @ units().T / 1000
    inputs = {
        "log_pixels": np.log1p(size),
        "log_frp_mean": np.where(none, np.nan, np.log1p(total / np.maximum(measured, 1))),
        "log_frp_max": np.where(none, np.nan, np.log1p(largest)),
        "log_span": np.log1p(reach.max(axis=1)),
        "reach_km_s": reach / 1000,
        "heat_km_s": np.where(none[:, None], np.nan, heat),
    }
    return inputs, centre, reach


def came_inputs(look: fronts.Look) -> dict[str, np.ndarray]:
    """Return how each front came to its place: its pixels on new ground near the known pixels,
    and its pixels far from each known pixel. `came_direction_deg` is for persistence, and
    `first_look` is the mark of a front with only such far pixels: they are not inputs."""
    labels, count = look.labels, look.labels.max() + 1
    size, near = np.bincount(labels, minlength=count), max(config.FRONT_REACH_M.values())
    distance, nearest = np.full(len(labels), np.inf), np.zeros(len(labels), dtype=int)
    if look.older is not None:
        distance, nearest = look.older.query(look.points)
    came = (distance > config.GROWTH_FLOOR_M) & (distance <= near)
    owner = labels[came]
    lines = look.points[came] - (look.older.data[nearest[came]] if came.any() else 0)
    sectors, found = _by_sector(owner, lines, count), fronts.mean_lines(owner, lines, count)
    total = np.maximum(sectors.sum(axis=1), 1)[:, None]
    mean = np.column_stack([np.bincount(owner, lines[:, i], minlength=count) for i in (0, 1)])
    lengths = np.bincount(owner, np.hypot(lines[:, 0], lines[:, 1]), minlength=count)
    fresh = np.bincount(labels, distance > near, minlength=count)
    return {
        "log_came": np.log1p(sectors.sum(axis=1)),
        "came_share": sectors.sum(axis=1) / size,
        "log_fresh": np.log1p(fresh),
        "first_look": fresh == size,
        "log_came_distance": np.log1p(np.nan_to_num(found["distance_m"])),
        # 1: the new ground is on one side of the front. 0: it is on all sides.
        "came_steady": np.hypot(mean[:, 0], mean[:, 1]) / np.maximum(lengths, 1e-9),
        "came_share_s": sectors / total,
        "came_adjacent_s": (np.roll(sectors, 1, axis=1) + np.roll(sectors, -1, axis=1)) / total,
        "came_direction_deg": found["direction_deg"],
    }


def older_inputs(look: fronts.Look) -> dict[str, np.ndarray]:
    """Return the ground that burned this season around each front, for each sector: the known
    pixels at the front (not farther than the link distance) and those farther, to the reach."""
    count = look.labels.max() + 1
    near, far = (np.zeros((count, config.FRONT_SECTORS)) for _ in range(2))
    if look.older is not None:
        known, limit = look.older.data, max(config.FRONT_REACH_M.values())
        distance, nearest = look.tree.query(known, distance_upper_bound=limit)
        found = np.isfinite(distance)
        owner, lines = look.labels[nearest[found]], known[found] - look.points[nearest[found]]
        at_front = distance[found] <= config.FRONT_LINK_M
        near = _by_sector(owner[at_front], lines[at_front], count)
        far = _by_sector(owner[~at_front], lines[~at_front], count)
    return {
        "log_older_near": np.log1p(near.sum(axis=1)),
        "log_older_far": np.log1p(far.sum(axis=1)),
        "log_older_near_s": np.log1p(near),
        "log_older_far_s": np.log1p(far),
        "older_near_share_s": near / np.maximum(near.sum(axis=1), 1)[:, None],
        "log_older_behind_s": np.log1p(np.roll(near, config.FRONT_SECTORS // 2, axis=1)),
    }


def _ground(layers: Layers, points: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return the cover group and the two burned shares at positions. Off the grid: 0."""
    grid = layer_grid()
    rows, cols = grid.rows_cols(*fronts.degrees(points))
    inside = (rows >= 0) & (rows < grid.height) & (cols >= 0) & (cols < grid.width)
    rows, cols = np.clip(rows, 0, grid.height - 1), np.clip(cols, 0, grid.width - 1)
    values = (layers.cover[rows, cols], layers.burned[0][rows, cols], layers.burned[1][rows, cols])
    return tuple(np.where(inside, value, 0) for value in values)


def ground_inputs(look: fronts.Look, layers: Layers, centre: np.ndarray, reach: np.ndarray) -> dict:
    """Return what each front burns, and what is ahead of it in each sector.

    The positions ahead are a fan past the edge of the front (`config.py`).
    """
    labels, count = look.labels, look.labels.max() + 1
    size, names = np.bincount(labels, minlength=count), list(config.COVER_GROUPS)
    group, last_year, before = _ground(layers, look.points)
    on = np.bincount(labels * (len(names) + 1) + group, minlength=count * (len(names) + 1))
    on = on.reshape(count, -1) / size[:, None]
    inputs = {f"on_{name}": on[:, names.index(name) + 1] for name in ON_FRONT}
    inputs["burned_last_year"] = np.bincount(labels, last_year, minlength=count) / size
    inputs["burned_before"] = np.bincount(labels, before, minlength=count) / size
    turns = np.deg2rad(config.FRONT_AHEAD_TURNS_DEG)
    centres = np.deg2rad(np.arange(config.FRONT_SECTORS) * 360 / config.FRONT_SECTORS)
    angle = centres[None, :, None, None] + turns[None, None, None, :]
    far = reach[:, :, None, None] + np.array(config.FRONT_AHEAD_M)[None, None, :, None]
    spots = centre[:, None, None, None, :] + far[..., None] * np.stack(
        [np.cos(angle), np.sin(angle)], axis=-1
    )
    group, last_year, before = _ground(layers, spots)
    inputs |= {
        f"ahead_{name}_s": (group == names.index(name) + 1).mean(axis=(2, 3)) for name in AHEAD
    }
    inputs["ahead_burned_last_year_s"] = last_year.mean(axis=(2, 3))
    inputs["ahead_burned_before_s"] = before.mean(axis=(2, 3))
    return inputs


def weather_inputs(layers: Layers, centre: np.ndarray, start: float, end: float) -> dict:
    """Return the weather before the look at the centre of each front. NaN: no weather on disk.

    The daily measures are for the days before the day of the look. The wind is the mean of the
    blocks before the block of the end of the look. `wind_direction_deg` is for the wind baseline.
    """
    grid = weather.weather_grid()
    rows, cols = grid.rows_cols(*fronts.degrees(centre))
    rows, cols = np.clip(rows, 0, grid.height - 1), np.clip(cols, 0, grid.width - 1)
    day = (datetime.fromtimestamp(start, UTC).date() - layers.first_day).days
    midnight = datetime(*layers.first_day.timetuple()[:3], tzinfo=UTC).timestamp()
    block = int((end - midnight) // (weather.BLOCK_HOURS * 3600))
    nothing = np.full(len(centre), np.nan)
    if day > len(layers.days["rain_mm"]) or block > len(layers.wind):
        names = ("past_vpd", "past_temp", "past_wind", "past_wind_speed", "wind_direction_deg")
        names += tuple(f"rain_{days}" for days in config.FRONT_RAIN_DAYS)
        return {name: nothing for name in names} | {
            "past_wind_toward_s": np.full((len(centre), config.FRONT_SECTORS), np.nan)
        }
    past = slice(day - config.FRONT_WEATHER_DAYS, day)
    inputs = {
        f"past_{name.split('_')[0]}": layers.days[name][past, rows, cols].mean(axis=0)
        for name in ("vpd_kpa", "temp_c", "wind_kmh")
    }
    for days in config.FRONT_RAIN_DAYS:
        inputs[f"rain_{days}"] = np.log1p(
            layers.days["rain_mm"][day - days : day, rows, cols].sum(axis=0)
        )
    east, north, speed = layers.wind[block - config.FRONT_WIND_BLOCKS : block, :, rows, cols].mean(
        axis=0
    )
    inputs["past_wind_speed"] = speed
    # How much of the wind goes to each sector, in km/h.
    inputs["past_wind_toward_s"] = np.column_stack([north, east]) @ units().T
    inputs["wind_direction_deg"] = np.degrees(np.arctan2(east, north)) % 360
    return inputs


def look_inputs(pixels: dict, bounds: tuple[int, int], look: fronts.Look, layers: Layers) -> dict:
    """Return the inputs of each front of a look."""
    a, b = bounds
    count = look.labels.max() + 1
    inputs, centre, reach = shape_inputs(look, pixels["frp_mw"][a:b])
    inputs["day_look"] = np.full(count, float(is_day_look(pixels["seconds"][a : a + 1])[0]))
    # The share of the pixels of a front that had fire at the look before: the fire stays active.
    first = np.searchsorted(pixels["look"], pixels["look"][a] - 1)
    again = np.zeros(b - a)
    if a > first:
        again = cKDTree(pixels["points"][first:a]).query(look.points)[0] <= config.GROWTH_FLOOR_M
    inputs["prev_share"] = np.bincount(look.labels, again, minlength=count) / np.bincount(
        look.labels
    )
    inputs |= came_inputs(look) | older_inputs(look) | ground_inputs(look, layers, centre, reach)
    sectors = units()
    inputs |= {
        "north_s": np.tile(sectors[:, 0], (count, 1)),
        "east_s": np.tile(sectors[:, 1], (count, 1)),
    }
    inputs |= weather_inputs(layers, centre, pixels["seconds"][a], pixels["seconds"][b - 1])
    return of_the_time(inputs, pixels["seconds"][a])


def of_the_time(inputs: dict, start: float) -> dict:
    """Return the inputs of a look with only the maps that existed at its start.

    The annual map of the burned ground of a year comes some months into the next year
    (`config.py`). A look before that month has no value for the inputs from that map.
    """
    if datetime.fromtimestamp(float(start), UTC).month >= config.FRONT_LAST_YEAR_FROM_MONTH:
        return inputs
    return inputs | {name: np.full(inputs[name].shape, np.nan) for name in LAST_YEAR}
