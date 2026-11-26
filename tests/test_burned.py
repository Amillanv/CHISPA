"""Tests of the burned share against a small real file: twelve cells of 2020."""

from pathlib import Path

import pytest

from chispa.sources import burned

SAMPLES = Path(__file__).parent / "samples"


def test_burned_share_of_a_cell_is_from_zero_to_one():
    share = burned.read_year(2020, SAMPLES)
    assert share.shape == (3, 4)
    # The file has percent as the map gave them: 96, 66, 71 and 25 in the first row.
    assert [round(float(value), 2) for value in share[0]] == [0.96, 0.66, 0.71, 0.25]
    assert [round(float(value), 2) for value in share[1]] == [1.0, 1.0, 0.03, 0.0]


def test_year_with_no_file_says_what_to_do():
    with pytest.raises(RuntimeError, match="chispa fetch burned --year 2019"):
        burned.read_year(2019, SAMPLES)
