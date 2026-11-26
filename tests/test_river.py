"""Tests of the river level against a small real file: the answer of ANA for September 2023."""

from datetime import date
from pathlib import Path

import pytest

from chispa.sources import river

SAMPLES = Path(__file__).parent / "samples"


def test_levels_of_a_month_come_from_the_row_with_the_most_days():
    # The answer has four rows for the month: one row with a level for each day, in
    # centimetres, and three rows with no level.
    levels = river.parse_file(SAMPLES / "river" / "2023.xml")
    assert len(levels) == 30
    assert (levels[date(2023, 9, 1)], levels[date(2023, 9, 15)]) == (3.77, 3.42)
    assert levels[date(2023, 9, 30)] == 2.8
    assert date(2023, 10, 1) not in levels


def test_days_of_the_years_are_one_series():
    assert river.read_days(SAMPLES, 2023, 2023)[date(2023, 9, 2)] == 3.74


def test_year_with_no_file_says_what_to_do():
    with pytest.raises(RuntimeError, match="chispa fetch river --year 2022"):
        river.read_days(SAMPLES, 2022, 2023)
