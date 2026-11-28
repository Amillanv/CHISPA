"""Tests of the command line."""

import pytest

from chispa import cli
from chispa.cli import NOT_BUILT, main


def test_help_lists_each_command(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    text = capsys.readouterr().out
    assert all(name in text for name in ["check", "fetch", "poll", "update", *NOT_BUILT])


def test_command_that_is_not_built_fails(capsys):
    with pytest.raises(SystemExit) as stop:
        main(["mcp"])
    assert stop.value.code == 1
    assert "not built" in capsys.readouterr().err


def test_result_command_for_a_test_year_needs_a_clear_decision(capsys):
    for command in ("evaluate", "severity"):
        with pytest.raises(SystemExit) as stop:
            main([command, "--year", "2025"])
        assert "test year of the later parts" in str(stop.value)
        assert "--test-run" in str(stop.value)


def test_poll_does_not_read_back_to_before_the_live_logs():
    with pytest.raises(SystemExit) as stop:
        main(["poll", "--since", "2026-11-01T00:00:00+00:00"])
    assert "The live logs start on 2026-11-20" in str(stop.value)


def test_update_makes_the_chance_of_a_front_after_the_growth_risk(monkeypatch, capsys):
    # The chance of a front reads the files that the growth risk makes in the same update.
    monkeypatch.setattr(cli, "open_store", lambda path: None)
    monkeypatch.setattr(cli, "add_live", lambda raw_dir, store: (0, 0))
    monkeypatch.setattr(cli, "stale_years", lambda store: [])
    status = {"late_at": None, "complete_pass_at": None}
    monkeypatch.setattr(cli.polls, "status", lambda raw_dir, now: status)
    monkeypatch.setattr(cli.forecast_live, "update", lambda *arguments: "forecast")
    monkeypatch.setattr(cli.checks, "update_risk", lambda project: "growth risk")
    monkeypatch.setattr(cli.checks, "update_front_chance", lambda: "front chance")
    cli.run_update()
    assert capsys.readouterr().out.splitlines()[-3:] == ["forecast", "growth risk", "front chance"]
