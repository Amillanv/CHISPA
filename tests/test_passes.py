"""Tests of the pass list, against a small real answer of the NASA service."""

from pathlib import Path

import numpy as np

from chispa.sources import passes

SAMPLES = Path(__file__).parent / "samples"


def test_file_gives_the_platform_the_time_and_the_outline(tmp_path):
    path = tmp_path / "VNP14IMG.json"
    path.write_text((SAMPLES / "cmr_vnp14img.json").read_text())
    granules = passes.parse_file(path)
    platform, start, outline = granules[0]
    assert len(granules) == 2
    assert platform == "SNPP"
    assert start == 1723698720.0  # 2024-08-15 05:12 UTC
    assert outline.shape == (5, 2)
    assert passes.covers(outline, -19.0, -57.0)  # The centre of the Pantanal box.
    assert not passes.covers(outline, 10.0, -57.0)


def test_outline_holds_a_position_inside_and_not_outside():
    square = np.array([[0.0, 0.0], [0.0, 2.0], [2.0, 2.0], [2.0, 0.0], [0.0, 0.0]])
    assert passes.covers(square, 1.0, 1.0)
    assert not passes.covers(square, 1.0, 3.0)
    assert not passes.covers(square, 3.0, 1.0)
