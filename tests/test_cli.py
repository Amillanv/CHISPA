"""Tests of the command line."""

import pytest

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
