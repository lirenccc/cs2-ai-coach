"""Normalized match/round/event records for SQLite indexes.

Raw demo_tick / server_tick are preserved; derived times are never stored as
replacements for tick domains.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RoundRecord:
    id: str
    match_id: str
    round_no: int
    freeze_end_demo_tick: int | None
    end_demo_tick: int | None
    end_marker_type: str | None
    winner: str | None = None
    win_reason: str | None = None


@dataclass(frozen=True, slots=True)
class RoundMarker:
    id: str
    match_id: str
    marker_type: str
    demo_tick: int
    server_tick: int | None
    sequence_index: int


@dataclass(frozen=True, slots=True)
class KillEventRecord:
    event_id: str
    match_id: str
    round_id: str | None
    demo_tick: int
    server_tick: int | None
    victim_userid: int | None
    victim_pawn_handle: int | None
    attacker_userid: int | None
    attacker_pawn_handle: int | None
    assister_userid: int | None
    assister_pawn_handle: int | None
    weapon: str | None
    headshot: bool
    penetrated: bool
    source_event_id: str
    source_parser: str | None


@dataclass(frozen=True, slots=True)
class DamageEventRecord:
    event_id: str
    match_id: str
    round_id: str | None
    demo_tick: int
    server_tick: int | None
    victim_userid: int | None
    victim_pawn_handle: int | None
    attacker_userid: int | None
    attacker_pawn_handle: int | None
    hp_damage: int
    armor_damage: int
    weapon: str | None
    source_event_id: str
    source_parser: str | None


@dataclass(frozen=True, slots=True)
class GrenadeEventRecord:
    event_id: str
    match_id: str
    round_id: str | None
    demo_tick: int
    server_tick: int | None
    grenade_type: str
    thrower_userid: int | None
    x: float | None
    y: float | None
    z: float | None
    source_event_id: str
    source_parser: str | None
