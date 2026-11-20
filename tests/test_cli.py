"""Tests of the command line."""

import pytest

from chispa.cli import NOT_BUILT, main


def test_help_lists_each_command(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    text = capsys.readouterr().out
    assert all(name in text for name in ["check", "fetch", *NOT_BUILT])


def test_command_that_is_not_built_fails(capsys):
    with pytest.raises(SystemExit) as stop:
        main(["fuse"])
    assert stop.value.code == 1
    assert "not built" in capsys.readouterr().err
