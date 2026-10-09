from __future__ import annotations

import math


def pre_roll_tick(
    anchor_tick: int,
    round_start_tick: int,
    seconds: float,
    ticks_per_second: float,
) -> int:
    # The caller supplies timing metadata. The domain never assumes 64/128 tick.
    if anchor_tick < 0 or round_start_tick < 0:
        raise ValueError("ticks must be non-negative")
    if round_start_tick > anchor_tick:
        raise ValueError("round_start_tick cannot be after anchor_tick")
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("seconds must be finite and non-negative")
    if not math.isfinite(ticks_per_second) or ticks_per_second <= 0:
        raise ValueError("ticks_per_second must be finite and positive")

    delta = int(round(seconds * ticks_per_second))
    return max(round_start_tick, anchor_tick - delta)
