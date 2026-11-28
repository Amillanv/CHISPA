"""Tests of the file of the live growth risk, with cases small enough for paper."""

import json
from datetime import UTC, date, datetime

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


def test_map_of_now_has_the_months_that_came_before_now(tmp_path, monkeypatch):
    monkeypatch.setattr("chispa.config.RISK_LIVE_DAYS", 30)
    monkeypatch.setattr("chispa.config.RISK_RECALIBRATION_WINDOW_DAYS", 365)
    published(tmp_path, 2023, {11: "2023-12-12T00:00:00+00:00", 12: "2024-01-14T00:00:00+00:00"})
    published(tmp_path, 2024, {6: "2024-07-11T00:00:00+00:00", 7: "2024-08-25T00:00:00+00:00"})
    # On 20 August the map of July was not there: it came on 25 August.
    assert risk_save.map_months(NOW, tmp_path) == {2023: 12, 2024: 6}
    assert monitor.months_on_disk(2024, tmp_path) == 7
    assert monitor.months_on_disk(2022, tmp_path) == 0
    # A download of August that stopped has a folder with no file `published.json`: it is not
    # a map, and the next look for a new month gets it again.
    (tmp_path / "monitor" / "2024-08").mkdir()
    assert monitor.months_on_disk(2024, tmp_path) == 7
    # On 5 January 2025 the new year has no month in the map. An answer of that day can be for
    # a moment of December, and its window of 365 days starts in 2023: three years.
    assert list(risk_save.outcome_years(datetime(2025, 1, 5, tzinfo=UTC))) == [2023, 2024, 2025]
    assert risk_save.map_months(datetime(2025, 1, 5, tzinfo=UTC), tmp_path) == {2023: 12, 2024: 7}
    assert list(risk_save.outcome_years(NOW)) == [2023, 2024]


def test_rows_stop_some_days_before_the_end_of_the_complete_weather(tmp_path, monkeypatch):
    folder = tmp_path / "weather" / "2024"
    folder.mkdir(parents=True)
    for name in ("05.npz", "06.npz", "07.npz.part"):
        (folder / name).write_bytes(b"")
    # June is the last complete month, and a row reads the weather of 3 days from its moment:
    # the rows stop 3 days before the last day of June.
    monkeypatch.setattr("chispa.config.RISK_WEATHER_DAYS", 3)
    assert risk_save.weather_until(NOW, tmp_path) == datetime(2024, 6, 27, tzinfo=UTC)
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
    ends = []

    def rows_of_month(year, month, end, paths):
        ends.append(end)
        return {"0": [dict(r) for r in rows]}

    monkeypatch.setattr(risk_save, "rows_of_month", rows_of_month)
    paths = (tmp_path / "store", tmp_path, NOW)
    past = risk_save.known_outcomes(parts, models, {2024: 6}, paths)["0h_100ha"]
    # The map has the months to June: an alert of July has no outcome in it. The weather is
    # complete to 20 August, and the rows stop at the end of June.
    assert ends == [datetime(2024, 6, 30, 23, 59, 59, tzinfo=UTC)]
    # The alert near an earlier alert and the alert with only GOES rows of INPE are left out.
    # The alert that the map puts on a known fire stays: a live alert does not have that mark.
    assert past["time"] == [DAY, 2 * DAY, 5 * DAY]
    assert past["large"] == [1.0, 0.0, 0.0]
    assert past["value"][0] > 0.5 > past["value"][1]


def test_file_is_made_again_only_for_a_new_month(tmp_path, monkeypatch):
    monkeypatch.setattr(risk_save, "pull_maps", lambda now, raw_dir, project: None)
    monkeypatch.setattr("chispa.sources.weather.download_year", lambda year, project, raw: [])
    monkeypatch.setattr(risk_save, "map_months", lambda now, raw_dir: {2024: 6})
    folder = tmp_path / "burnday" / "2024"
    folder.mkdir(parents=True)
    for month in (1, 2, 3):
        (folder / f"{month:02d}.npz").write_bytes(b"")
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
        "The maps have no new month."
    )
    saved = risk_files.load_models(path)
    assert (saved["made_at"], saved["map_checked_at"]) == (to_text(NOW), to_text(later))
    assert (saved["map"], saved["burn_days"]) == ({"2024": 6}, {"2024": 3})
    # The burn days of April come, and the fit of that day fails: the saved file stays. The
    # next look still sees maps that are not those of the saved file, and it makes it again.
    (folder / "04.npz").write_bytes(b"")

    def fails(year, store, raw):
        raise RuntimeError("no layer")

    monkeypatch.setattr(risk_save, "year_parts", fails)
    with pytest.raises(RuntimeError, match="no layer"):
        risk_save.refresh(tmp_path / "store", tmp_path, later, "project")
    monkeypatch.setattr(risk_save, "year_parts", lambda year, store, raw: parts_of()[year])
    line = risk_save.refresh(tmp_path / "store", tmp_path, later.replace(day=22), "project")
    assert line.startswith("New saved models")
    assert risk_files.load_models(path)["burn_days"] == {"2024": 4}
    # The burn days of June and of later months are not read for a map to June.
    for month in (5, 6, 7):
        (folder / f"{month:02d}.npz").write_bytes(b"")
    assert risk_save.made_from(later, tmp_path)["burn_days"] == {"2024": 5}


def test_month_of_burn_days_can_be_absent_only_while_the_product_is_late(tmp_path, monkeypatch):
    monkeypatch.setattr("chispa.config.BURNDAY_LATE_DAYS", 60)
    for year, months in ((2026, 10), (2025, 10)):
        folder = tmp_path / "burnday" / str(year)
        folder.mkdir(parents=True)
        for month in range(1, months + 1):
            np.savez_compressed(folder / f"{month:02d}.npz", day=np.ones((2, 2), dtype=np.uint16))
    # On 20 January 2027, November 2026 ended 51 days before: the product can be without it.
    monkeypatch.setattr(burnday, "_today", lambda: date(2027, 1, 20))
    found = burnday.read_year(2026, tmp_path)
    assert found.shape == (12, 2, 2) and found[9].all() and not found[10].any()
    # 2025 with no file for November is a download that stopped: its end was long before.
    with pytest.raises(RuntimeError, match="fetch burnday --year 2025"):
        burnday.read_year(2025, tmp_path)
    # On 1 March 2027, November 2026 ended 91 days before: its file must be there.
    monkeypatch.setattr(burnday, "_today", lambda: date(2027, 3, 1))
    with pytest.raises(RuntimeError, match="fetch burnday --year 2026"):
        burnday.read_year(2026, tmp_path)
    # A new year with no file: on 20 February the product is without January, and no month has
    # a burn day.
    monkeypatch.setattr(burnday, "_today", lambda: date(2027, 2, 20))
    assert not burnday.read_year(2027, tmp_path).any()
