from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Kill:
    tick: int
    attacker_id: str
    victim_id: str


def is_opening_death(kills: list[Kill], focus_player_id: str) -> bool:
    """True when focus is among victims at the earliest DemoTick.

    Same-tick multi-kills are all opening deaths; list order must not matter.
    """

    if not kills:
        return False
    min_tick = min(kill.tick for kill in kills)
    return any(
        kill.tick == min_tick and kill.victim_id == focus_player_id for kill in kills
    )


def is_untraded_death(
    kills: list[Kill],
    focus_player_id: str,
    teammate_ids: set[str],
    trade_window_ticks: int,
) -> bool:
    if trade_window_ticks < 0:
        raise ValueError("trade_window_ticks must be non-negative")

    deaths = sorted(
        (k for k in kills if k.victim_id == focus_player_id),
        key=lambda k: k.tick,
    )
    if not deaths:
        return False

    death = deaths[0]
    killer_id = death.attacker_id

    for kill in kills:
        if (
            death.tick <= kill.tick <= death.tick + trade_window_ticks
            and kill.attacker_id in teammate_ids
            and kill.victim_id == killer_id
        ):
            return False
    return True
