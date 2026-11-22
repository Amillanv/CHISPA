"""Tests of the fusion rules, with cases small enough for paper."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from chispa.fusion import fuse
from chispa.models import Detection

T0 = datetime(2024, 8, 15, 5, 0, tzinfo=UTC)
# One VIIRS detection in the Pantanal. Its footprint plus the margin reaches 700 m.
VIIRS = Detection(
    source="firms",
    sensor_family="viirs",
    platform="SNPP",
    observed_at=T0,
    available_at=T0 + timedelta(hours=3),
    lat=-17.5,
    lon=-57.5,
    footprint_m=200.0,
    frp_mw=5.0,
    source_confidence="nominal",
)
KM = 1 / 110.574  # one kilometre north, in degrees


def later(detection, **delta):
    step = timedelta(**delta)
    return replace(
        detection,
        observed_at=detection.observed_at + step,
        available_at=detection.available_at + step,
    )


def run(*detections):
    ordered = sorted(enumerate(detections), key=lambda pair: pair[1].available_at)
    return fuse(ordered, first_id=100)


def test_near_detections_are_one_event():
    events, _, members = run(VIIRS, replace(VIIRS, lat=VIIRS.lat + 0.5 * KM))
    assert len(events) == 1
    assert events[0].detections == 2
    assert {event_id for _, event_id, _ in members} == {100}


def test_far_detections_are_two_events():
    events, _, _ = run(VIIRS, replace(VIIRS, lat=VIIRS.lat + 10 * KM))
    assert [event.id for event in events] == [100, 101]


def test_same_place_after_the_time_window_is_a_new_event():
    events, _, _ = run(VIIRS, later(VIIRS, hours=25))
    assert len(events) == 2


def test_detection_between_two_events_merges_them_into_the_older():
    north = replace(VIIRS, lat=VIIRS.lat + 2.4 * KM, platform="NOAA20")
    bridge = later(replace(VIIRS, lat=VIIRS.lat + 1.2 * KM), hours=1)
    events, alerts, members = run(VIIRS, north, bridge)
    assert [(event.id, event.detections) for event in events] == [(100, 3)]
    assert {event_id for _, event_id, _ in members} == {100}
    assert {alert.event_id for alert in alerts} == {100}
    # Each of the two first events was LOW. The merged event has LOW one time, then MEDIUM.
    assert [alert.level for alert in alerts] == ["LOW", "MEDIUM"]


def test_one_nominal_detection_is_low():
    events, alerts, _ = run(VIIRS)
    assert events[0].level == "LOW"
    assert [(alert.level, alert.at) for alert in alerts] == [("LOW", VIIRS.available_at)]


def test_same_pass_from_two_sources_is_one_item_of_evidence():
    inpe = later(replace(VIIRS, source="inpe"), minutes=1)
    events, _, _ = run(VIIRS, inpe)
    assert (events[0].level, events[0].passes) == ("LOW", 1)


def test_second_pass_of_the_same_family_is_medium():
    events, alerts, _ = run(VIIRS, later(VIIRS, minutes=100))
    assert (events[0].level, events[0].passes) == ("MEDIUM", 2)
    assert [alert.level for alert in alerts] == ["LOW", "MEDIUM"]


def test_high_source_confidence_is_medium():
    events, _, _ = run(replace(VIIRS, source_confidence="high"))
    assert events[0].level == "MEDIUM"


def test_two_sensor_families_are_high():
    goes = replace(VIIRS, sensor_family="abi", platform="GOES16", footprint_m=1250.0)
    events, alerts, members = run(VIIRS, later(goes, minutes=30))
    assert (events[0].level, events[0].families) == ("HIGH", "abi+viirs")
    assert [level for _, _, level in members] == ["LOW", "HIGH"]
    assert alerts[-1].at == goes.available_at + timedelta(minutes=30)


def test_goes_times_of_one_scan_from_two_sources_are_one_pass():
    goes = replace(VIIRS, sensor_family="abi", platform="GOES16", footprint_m=1250.0)
    inpe = later(replace(goes, source="inpe"), minutes=6, seconds=51)
    next_scan = later(goes, minutes=10)
    assert run(goes, inpe)[0][0].passes == 1
    assert run(goes, next_scan)[0][0].passes == 2


def test_event_summary():
    north = replace(VIIRS, lat=VIIRS.lat + 0.5 * KM, frp_mw=9.0)
    event = run(VIIRS, later(north, minutes=100))[0][0]
    assert (event.south, event.north) == (VIIRS.lat, north.lat)
    assert event.max_frp_mw == 9.0
    assert event.first_available_at == VIIRS.available_at
    assert event.last_observed_at == T0 + timedelta(minutes=100)
