from __future__ import annotations

import math
import pytest

from app.domain.timing import pre_roll_tick


def test_pre_roll_uses_supplied_tick_rate():
    assert pre_roll_tick(1000, 100, seconds=2, ticks_per_second=64) == 872
    assert pre_roll_tick(1000, 100, seconds=2, ticks_per_second=128) == 744


def test_pre_roll_clamps_to_round_start():
    assert pre_roll_tick(150, 100, seconds=10, ticks_per_second=64) == 100


def test_zero_pre_roll_returns_anchor():
    assert pre_roll_tick(150, 100, seconds=0, ticks_per_second=64) == 150


@pytest.mark.parametrize(
    "args",
    [
        (-1, 0, 1, 64),
        (10, -1, 1, 64),
        (10, 11, 1, 64),
        (10, 0, -1, 64),
        (10, 0, math.nan, 64),
        (10, 0, 1, 0),
        (10, 0, 1, -64),
        (10, 0, 1, math.inf),
    ],
)
def test_invalid_timing_inputs_raise(args):
    with pytest.raises(ValueError):
        pre_roll_tick(*args)
