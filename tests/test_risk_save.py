"""Tests of the file of the live growth risk, with cases small enough for paper."""

import json
from datetime import UTC, datetime

import numpy as np
import pytest

from chispa import risk_files
from chispa.evaluation import risk_save
from chispa.sources import burnday, monitor
from chispa.store import to_text

NOW = datetime(2024, 8, 20, tzinfo=UTC)
DAY = 86_400.0


@pytest.fixture(autouse=True)
def settings(monkeypatch, tmp_path):
    monkeypatch.setattr("chispa.config.RISK_MODELS_PATH", tmp_path / "risk_models.json")
    monkeypatch.setattr("chispa.config.RISK_CLASS_LIMITS_HA", (100.0,))
    monkeypatch.setattr("chispa.config.YEAR_ROLES", {2022: "a", 2023: "b"})
    monkeypatch.setattr("chispa.evaluation.risk.names_of", lambda moment: ("x",))
    monkeypatch.setattr("chispa.evaluation.risk.ADOPTED", ())
    monkeypatch.setattr("chispa.evaluation.risk.REMOVED", ())
    monkeypatch.setattr(risk_save, "MOMENTS", ("0",))
    monkeypatch.setattr("chispa.evaluation.risk.MOMENTS", ("0",))
    monkeypatch.setattr("chispa.evaluation.risk_recalibration.MOMENTS", ("0",))


def published(raw_dir, year: int, months: dict[int, str]) -> None:
    folder = raw_dir / "monitor" / f"{year}-{max(months):02d}"
    folder.mkdir(parents=True)
    (folder / "published.json").write_text(json.dumps(months))


def test_map_of_now_has_the_months_that_came_before_now(tmp_path):
    published(tmp_path, 2023, {11: "2023-12-12T00:00:00+00:00", 12: "2024-01-14T00:00:00+00:00"})
    published(tmp_path, 2024, {6: "2024-07-11T00:00:00+00:00", 7: "2024-08-25T00:00:00+00:00"})
    # On 20 August the map of July was not there: it came on 25 August.
    assert risk_save.map_months(NOW, tmp_path) == {2023: 12, 2024: 6}
    assert (monitor.months_on_disk(2024, tmp_path), monitor.months_on_disk(2022, tmp_path)) == (
        7,
        0,
    )
    # On 5 January 2025 the new year has no month in the map.
    assert risk_save.map_months(datetime(2025, 1, 5, tzinfo=UTC), tmp_path) == {2024: 7}


def test_rows_stop_some_days_before_the_end_of_the_complete_weather(tmp_path):
    folder = tmp_path / "weather" / "2024"
    folder.mkdir(parents=True)
    for name in ("05.npz", "06.npz", "07.npz.part"):
        (folder / name).write_bytes(b"")
    # June is the last complete month: the rows stop 5 days before the end of 30 June.
    assert risk_save.weather_until(NOW, tmp_path) == datetime(2024, 6, 25, tzinfo=UTC)
    with pytest.raises(RuntimeError, match="fetch weather"):
        risk_save.weather_until(NOW, tmp_path / "absent")


def alert(x: float, size_ha: float, day: float = 0.0, **marks) -> dict:
    row = {"inputs": {"x": x}, "size_ha": size_ha, "at": day * DAY, "matched": size_ha > 0}
    return row | {"known": False, "near_earlier": False, "only_inpe_goes": False} | marks


def parts_of() -> dict:
    """Two years in which an alert with x of 1 becomes large, and one with x of 0 does not."""
    rows = [alert(float(n % 2), 500.0 * (n % 2)) for n in range(20)]
    return {year: {"rows": {"0": rows + [alert(0.0, 500.0, known=True)]}} for year in (2022, 2023)}


def test_models_have_the_values_of_their_alerts_in_sequence():
    model = risk_save.fit(parts_of(), [2022, 2023])["0h_100ha"]
    # The 40 alerts that are not on a known fire gave the weights: 20 small and 20 large values.
    reference = np.array(model["reference"])
    assert len(reference) == 40 and (np.diff(reference) >= 0).all()
    assert reference[19] < 0.5 < reference[20]


def test_outcomes_are_those_of_the_alerts_that_a_live_alert_can_be(tmp_path, monkeypatch):
    parts = parts_of()
    models = risk_save.fit(parts, [2022, 2023])
    monkeypatch.setattr(risk_save, "weather_until", lambda now, raw_dir: NOW)
    rows = [alert(1.0, 500.0, day=1.0), alert(0.0, 0.0, day=2.0)]
    rows += [alert(1.0, 500.0, day=3.0, near_earlier=True)]
    rows += [alert(1.0, 500.0, day=4.0, only_inpe_goes=True), alert(1.0, 0.0, day=5.0, known=True)]
    monkeypatch.setattr(risk_save, "rows_of_month", lambda *_: {"0": [dict(r) for r in rows]})
    paths = (tmp_path / "store", tmp_path, NOW)
    past = risk_save.known_outcomes(parts, models, {2024: 6}, paths)["0h_100ha"]
    # The alert near an earlier alert and the alert with only GOES rows of INPE are left out.
    # The alert that the map puts on a known fire stays: a live alert does not have that mark.
    assert past["time"] == [DAY, 2 * DAY, 5 * DAY]
    assert past["large"] == [1.0, 0.0, 0.0]
    assert past["value"][0] > 0.5 > past["value"][1]


def test_file_is_made_again_only_for_a_new_month(tmp_path, monkeypatch):
    monkeypatch.setattr(risk_save, "pull_maps", lambda now, raw_dir, project: 0)
    monkeypatch.setattr(risk_save, "map_months", lambda now, raw_dir: {2024: 6})
    monkeypatch.setattr(risk_save, "year_parts", lambda year, store, raw: parts_of()[year])
    monkeypatch.setattr(risk_save, "known_outcomes", lambda *_: {"0h_100ha": {"time": [1.0]}})
    path = tmp_path / "risk_models.json"
    line = risk_save.refresh(tmp_path / "store", tmp_path, NOW, "project")
    assert line == "New saved models and outcomes: the Monitor map to {'2024': 6}."
    saved = risk_files.load_models(path)
    assert (saved["fit_years"], saved["map"], saved["made_at"]) == (
        [2022, 2023],
        {"2024": 6},
        to_text(NOW),
    )
    assert list(saved["models"]) == ["0h_100ha"] and saved["past"] == {"0h_100ha": {"time": [1.0]}}
    # One day later the map has no new month: the models stay, and the time of the look moves.
    monkeypatch.setattr(risk_save, "year_parts", None)
    later = NOW.replace(day=21)
    assert risk_save.refresh(tmp_path / "store", tmp_path, later, "project") == (
        "The Monitor map has no new month."
    )
    saved = risk_files.load_models(path)
    assert (saved["made_at"], saved["map_checked_at"]) == (to_text(NOW), to_text(later))


def test_burn_days_of_the_year_before_can_be_in_progress(tmp_path):
    this_year = datetime.now(UTC).year
    for year, months in ((this_year - 1, 10), (this_year - 2, 10)):
        folder = tmp_path / "burnday" / str(year)
        folder.mkdir(parents=True)
        for month in range(1, months + 1):
            np.savez_compressed(folder / f"{month:02d}.npz", day=np.ones((2, 2), dtype=np.uint16))
    # The product has a month some weeks after its end: in January the year before has no
    # file for its last months. An older year with no file for a month is not complete.
    found = burnday.read_year(this_year - 1, tmp_path)
    assert found.shape == (12, 2, 2) and found[9].all() and not found[10].any()
    with pytest.raises(RuntimeError, match="fetch burnday"):
        burnday.read_year(this_year - 2, tmp_path)
