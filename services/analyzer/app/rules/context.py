"""Normalized inputs consumed by pure deterministic rules."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.evidence import EvidenceCertainty, RoundPlayerState
from .thresholds import RuleThresholds


@dataclass(frozen=True, slots=True)
class LifeEndingEvent:
    """Authoritative-enough life-ending fact for alive-state reconstruction.

    Identity fields use PlayerIdentity / ControllerSession / PawnLife ids when
    known. Display names are never keys.
    """

    event_id: str
    demo_tick: int
    round_no: int
    victim_identity_id: str | None
    attacker_identity_id: str | None = None
    victim_controller_session_id: str | None = None
    victim_pawn_life_id: str | None = None
    attacker_controller_session_id: str | None = None
    attacker_pawn_life_id: str | None = None
    victim_side: str | None = None
    attacker_side: str | None = None
    certainty: EvidenceCertainty = EvidenceCertainty.VERIFIED
    is_suicide: bool = False
    is_teamkill: bool = False
    # P0.6A: trade / ownership across unresolved takeover must not guess.
    crosses_unresolved_takeover: bool = False


@dataclass(frozen=True, slots=True)
class RoundSnapshot:
    """One round of authoritative side / outcome / starting alive state."""

    round_id: str
    round_no: int
    freeze_end_demo_tick: int | None
    end_demo_tick: int | None
    winner: str | None
    win_reason: str | None
    # player_identity_id -> side ("ct" | "t"); from RoundPlayerState contract
    player_sides: dict[str, str]
    side_source: str
    # player_identity_id set known alive at freeze_end (authoritative)
    initial_alive_identity_ids: frozenset[str]
    # True when freeze_end alive/side provenance is incomplete for this round
    alive_provenance_complete: bool = True


@dataclass(frozen=True, slots=True)
class RuleContext:
    """Pure structured match slice — no AI / capture / NetCon handles."""

    match_id: str
    rounds: tuple[RoundSnapshot, ...]
    life_ending_events: tuple[LifeEndingEvent, ...]
    thresholds: RuleThresholds = field(default_factory=RuleThresholds)
    round_player_states: tuple[RoundPlayerState, ...] = ()

    def rounds_by_no(self) -> dict[int, RoundSnapshot]:
        return {item.round_no: item for item in self.rounds}

    def events_for_round(self, round_no: int) -> tuple[LifeEndingEvent, ...]:
        return tuple(
            event
            for event in self.life_ending_events
            if event.round_no == round_no
        )
