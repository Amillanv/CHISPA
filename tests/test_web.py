"""Tests of the dashboard server: each route gives the answer of its tool, or a clear error."""

import json
import threading
from datetime import timedelta
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from chispa import tools
from chispa.web.server import Handler
from tests.test_fusion import T0
from tests.test_tools import store  # noqa: F401  The fixture: a store with two events.


@pytest.fixture
def address(store):  # noqa: F811
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def get(url: str) -> tuple[int, dict | str]:
    try:
        with urlopen(url) as answer:
            body = answer.read().decode()
            kind = answer.headers["Content-Type"]
            return answer.status, json.loads(body) if kind.startswith("application/json") else body
    except HTTPError as error:
        return error.code, json.loads(error.read().decode())


def test_alerts_route_gives_the_events_of_the_tool(address):
    as_of = T0 + timedelta(hours=6)
    status, answer = get(f"{address}/api/alerts?as_of={as_of.isoformat().replace('+', '%2B')}")
    assert status == 200
    expected = tools.alerts_near(-19.0, -57.0, 500.0, 24.0, as_of)
    assert answer["events"] == json.loads(json.dumps(expected))
    assert len(answer["events"]) == 2


def test_event_and_activity_routes_call_their_tools(address):
    as_of = (T0 + timedelta(hours=6)).isoformat().replace("+", "%2B")
    status, record = get(f"{address}/api/event/100?as_of={as_of}")
    assert (status, record["level"], record["growth_steps"]) == (200, "HIGH", [])
    status, found = get(f"{address}/api/activity?as_of={as_of}&hours=6&step_hours=3")
    assert (status, len(found["steps"])) == (200, 2)


def test_bad_argument_gives_400_with_the_reason(address):
    status, answer = get(f"{address}/api/event/abc")
    assert (status, answer["error"]) == (400, "'abc' is not a whole number.")
    status, answer = get(f"{address}/api/activity?hours=6")
    assert (status, answer["error"]) == (400, "Give step_hours as a number.")
    status, answer = get(f"{address}/api/alerts?as_of=2024-08-15T05:00:00")
    assert status == 400 and "timezone" in answer["error"]


def test_page_is_served_and_a_path_out_of_the_static_folder_is_not(address):
    status, page = get(f"{address}/")
    assert status == 200 and "<title>" in page
    status, _ = get(f"{address}/static/..%2Fserver.py")
    assert status == 404
