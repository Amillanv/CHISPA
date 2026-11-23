"""The dashboard server: one page, its static files and the JSON routes that call the tools.

The page shows what CHISPA knows about the Pantanal at an as-of time, and how much to trust it.
This module contains no logic. It reads the arguments, calls `tools.py` and returns the answers.
It uses the HTTP server of the standard library: one process, and no new dependency.
"""

import json
import mimetypes
import os
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from chispa import config, tools
from chispa.fusion import LEVELS
from chispa.store import to_text

STATIC = (Path(__file__).parent / "static").resolve()
JSON = "application/json; charset=utf-8"
Answer = tuple[int, bytes, str]


def serve(port: int) -> None:
    """Serve the dashboard on this computer only, until the process stops."""
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"The dashboard is at http://127.0.0.1:{port}/. Push Ctrl+C to stop it.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


class Handler(BaseHTTPRequestHandler):
    """Send each request to its route. A rejected argument gives a JSON answer with its reason."""

    def do_GET(self) -> None:
        url = urlsplit(self.path)
        arguments = {name: values[-1] for name, values in parse_qs(url.query).items()}
        try:
            status, body, kind = route(url.path, arguments)
        except ValueError as error:  # A tool rejected an argument. The message says what to do.
            status, body, kind = HTTPStatus.BAD_REQUEST, _json({"error": str(error)}), JSON
        except RuntimeError as error:  # The store or a result file is absent.
            status, body, kind = HTTPStatus.SERVICE_UNAVAILABLE, _json({"error": str(error)}), JSON
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def route(path: str, arguments: dict[str, str]) -> Answer:
    """Return the status, the body and the content type for one request."""
    if path == "/":
        return _file(STATIC / "index.html", STATIC)
    if path.startswith("/static/"):
        return _file(STATIC / path.removeprefix("/static/"), STATIC)
    if path == "/api/border":
        folder = (config.RAW_DIR / "border").resolve()
        return _file(folder / "pantanal.geojson", folder)
    if path == "/api/settings":
        return HTTPStatus.OK, _json(settings()), JSON
    as_of = as_of_argument(arguments)
    if path == "/api/alerts":
        lat, lon = config.DASHBOARD_CENTRE
        since = config.DASHBOARD_SINCE_HOURS
        events = tools.alerts_near(lat, lon, config.DASHBOARD_RADIUS_KM, since, as_of)
        answer = {"as_of": to_text(as_of), "since_hours": since, "events": events}
    elif path.startswith("/api/event/"):
        answer = tools.event_record(_integer(path.removeprefix("/api/event/")), as_of)
    elif path == "/api/activity":
        hours, step = number(arguments, "hours"), number(arguments, "step_hours")
        answer = tools.activity(hours, step, as_of)
    elif path == "/api/live":
        answer = tools.live_status(as_of)
    elif path.startswith("/api/evaluation/"):
        answer = tools.evaluation_summary(_integer(path.removeprefix("/api/evaluation/")))
    else:
        return HTTPStatus.NOT_FOUND, _json({"error": f"No route {path}."}), JSON
    return HTTPStatus.OK, _json(answer), JSON


def settings() -> dict:
    """Return the values of `config.py` that the page needs. The page has no value of its own."""
    return {
        "map_key": os.environ.get("MAPTILER_KEY", ""),
        "box": config.PANTANAL_BOX,
        "since_hours": config.DASHBOARD_SINCE_HOURS,
        "windows": [{"hours": h, "step_hours": s} for h, s in config.DASHBOARD_WINDOWS],
        "refresh_s": config.DASHBOARD_REFRESH.total_seconds(),
        "time_zone": config.DASHBOARD_TIME_ZONE,
        "live_start": to_text(config.LIVE_START),
        "replays": [to_text(moment) for moment in config.DASHBOARD_REPLAYS],
        "levels": LEVELS,
        "evaluated_years": [config.DEVELOPMENT_YEAR, config.TEST_YEAR],
        "test_year": config.TEST_YEAR,
        "confidence_year": config.DEVELOPMENT_YEAR,
        "confidence_moments_h": {
            "0": config.PASS_GAP.total_seconds() / 3600,
            "24": config.SEVERITY_EVAL_HOURS,
        },
        "growth_floor_m": config.GROWTH_FLOOR_M,
        "growth_speed_min_h": config.GROWTH_SPEED_MIN_H,
        "severity_points": {
            "power": config.SEVERITY_POWER_POINTS,
            "extent": config.SEVERITY_EXTENT_POINTS,
            "advance": config.SEVERITY_ADVANCE_POINTS,
            "cover": max(config.SEVERITY_COVER_POINTS.values()),
            "people": config.SEVERITY_PEOPLE_POINTS,
            "land": config.SEVERITY_LAND_POINTS,
        },
    }


def as_of_argument(arguments: dict[str, str]) -> datetime:
    """Return the `as_of` argument as a UTC time. With no argument it is the time of the request."""
    text = arguments.get("as_of")
    if not text:
        return datetime.now(UTC).replace(microsecond=0)
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        raise ValueError(f"as_of is not an ISO 8601 time: {text!r}.") from None
    if moment.utcoffset() is None:
        raise ValueError("as_of has no timezone. Write the time in UTC, with Z at the end.")
    return moment


def number(arguments: dict[str, str], name: str) -> float:
    """Return a numeric argument. An absent or bad value is rejected with its name."""
    try:
        return float(arguments[name])
    except (KeyError, ValueError):
        raise ValueError(f"Give {name} as a number.") from None


def _integer(text: str) -> int:
    if not text.isdigit():
        raise ValueError(f"{text!r} is not a whole number.")
    return int(text)


def _file(path: Path, folder: Path) -> Answer:
    """Return a file of the folder, or 404. A path out of the folder gets 404."""
    target = path.resolve()
    if not (target.is_relative_to(folder) and target.is_file()):
        return HTTPStatus.NOT_FOUND, _json({"error": f"No file {path.name}."}), JSON
    kind = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    if target.suffix == ".geojson":
        kind = "application/geo+json"
    return HTTPStatus.OK, target.read_bytes(), kind


def _json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode()
