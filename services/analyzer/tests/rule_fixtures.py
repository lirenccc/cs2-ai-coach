"""Shared builders for deterministic rule-engine unit tests."""

from __future__ import annotations

from app.domain.evidence import EvidenceCertainty
from app.rules.context import LifeEndingEvent, RoundSnapshot, RuleContext
from app.rules.thresholds import RuleThresholds


def round_snap(
    *,
    round_no: int = 1,
    round_id: str | None = None,
    winner: str | None = "t",
    win_reason: str | None = "elimination",
    sides: dict[str, str],
    alive: set[str] | frozenset[str] | None = None,
    freeze_end: int = 100,
    end_tick: int = 500,
    side_source: str = "test.tick.side",
    complete: bool = True,
) -> RoundSnapshot:
    alive_ids = frozenset(alive if alive is not None else sides.keys())
    return RoundSnapshot(
        round_id=round_id or f"r{round_no}",
        round_no=round_no,
        freeze_end_demo_tick=freeze_end,
        end_demo_tick=end_tick,
        winner=winner,
        win_reason=win_reason,
        player_sides=dict(sides),
        side_source=side_source,
        initial_alive_identity_ids=alive_ids,
        alive_provenance_complete=complete,
    )


def death(
    event_id: str,
    tick: int,
    victim: str,
    attacker: str | None = None,
    *,
    round_no: int = 1,
    victim_side: str | None = None,
    attacker_side: str | None = None,
    unresolved_takeover: bool = False,
    certainty: EvidenceCertainty = EvidenceCertainty.VERIFIED,
    suicide: bool = False,
    teamkill: bool = False,
    pawn_life_id: str | None = None,
) -> LifeEndingEvent:
    return LifeEndingEvent(
        event_id=event_id,
        demo_tick=tick,
        round_no=round_no,
        victim_identity_id=victim,
        attacker_identity_id=attacker,
        victim_side=victim_side,
        attacker_side=attacker_side,
        certainty=certainty,
        is_suicide=suicide or (attacker is None or attacker == victim),
        is_teamkill=teamkill,
        crosses_unresolved_takeover=unresolved_takeover,
        victim_pawn_life_id=pawn_life_id,
    )


def ctx(
    rounds: list[RoundSnapshot],
    events: list[LifeEndingEvent],
    *,
    match_id: str = "match_test",
    minimum_player_advantage: int = 2,
    trade_window_demo_ticks: int = 20,
) -> RuleContext:
    return RuleContext(
        match_id=match_id,
        rounds=tuple(rounds),
        life_ending_events=tuple(events),
        thresholds=RuleThresholds(
            minimum_player_advantage=minimum_player_advantage,
            trade_window_demo_ticks=trade_window_demo_ticks,
        ),
    )


def five_v_five_sides() -> dict[str, str]:
    return {
        "CT1": "ct",
        "CT2": "ct",
        "CT3": "ct",
        "CT4": "ct",
        "CT5": "ct",
        "T1": "t",
        "T2": "t",
        "T3": "t",
        "T4": "t",
        "T5": "t",
    }
