"""Versioned, explicit rule thresholds — no scattered magic numbers."""

from __future__ import annotations

from dataclasses import dataclass


RULE_THRESHOLDS_VERSION = "rule-thresholds-v1-2026-10-10"


@dataclass(frozen=True, slots=True)
class RuleThresholds:
    """Configurable deterministic parameters shared by the first rule batch."""

    version: str = RULE_THRESHOLDS_VERSION
    # R002: trade window length in DemoTick units (caller supplies timing; never
    # assume a global 64-tick rate when converting wall-clock seconds).
    trade_window_demo_ticks: int = 320
    # R003: minimum (friendly_alive - enemy_alive) that qualifies as advantage.
    minimum_player_advantage: int = 2

    def __post_init__(self) -> None:
        if self.trade_window_demo_ticks < 0:
            raise ValueError("trade_window_demo_ticks must be non-negative")
        if self.minimum_player_advantage < 1:
            raise ValueError("minimum_player_advantage must be >= 1")
