"""Normalized demo parse results.

Parser-specific DataFrames must be converted to these shapes at the adapter
boundary and must never escape into FastAPI handlers.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


NORMALIZATION_SCHEMA_VERSION = "2"


@dataclass(frozen=True, slots=True)
class MatchHeader:
    map_name: str | None
    patch_version: str | None = None
    build_num: str | None = None
    demo_version_name: str | None = None
    server_name: str | None = None
    client_name: str | None = None
    tick_rate: float | None = None
    playback_ticks: int | None = None
    playback_time_seconds: float | None = None
    server_start_tick: int | None = None
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PlayerRosterEntry:
    player_id: str
    steamid64: str | None
    display_name: str | None
    team: str | None = None
    is_bot: bool = False
    is_hltv: bool = False
    userid: int | None = None
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RoundRow:
    round_number: int
    freeze_end_tick: int | None
    end_tick: int | None
    winner: str | None = None
    win_reason: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class KillRow:
    event_id: str
    tick: int
    attacker_id: str | None
    victim_id: str
    assister_id: str | None = None
    weapon: str | None = None
    headshot: bool = False
    penetrated: bool = False
    round_number: int | None = None
    demo_tick: int | None = None
    server_tick: int | None = None
    victim_userid: int | None = None
    victim_pawn: int | None = None
    attacker_userid: int | None = None
    attacker_pawn: int | None = None
    assister_userid: int | None = None
    assister_pawn: int | None = None
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DamageRow:
    event_id: str
    tick: int
    attacker_id: str | None
    victim_id: str
    hp_damage: int
    armor_damage: int = 0
    weapon: str | None = None
    round_number: int | None = None
    demo_tick: int | None = None
    server_tick: int | None = None
    victim_userid: int | None = None
    victim_pawn: int | None = None
    attacker_userid: int | None = None
    attacker_pawn: int | None = None
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GrenadeRow:
    event_id: str
    tick: int
    grenade_type: str
    thrower_id: str | None
    x: float | None = None
    y: float | None = None
    z: float | None = None
    round_number: int | None = None
    demo_tick: int | None = None
    server_tick: int | None = None
    thrower_userid: int | None = None
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SelectedTickRow:
    demo_tick: int
    player_id: str
    steamid64: str | None
    x: float | None
    y: float | None
    z: float | None
    health: float | None
    team: str | None
    is_alive: bool | None
    selection_reason: str
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ParsedDemo:
    parser_name: str
    parser_version: str | None
    normalization_schema_version: str
    header: MatchHeader
    roster: list[PlayerRosterEntry]
    rounds: list[RoundRow]
    kills: list[KillRow]
    damages: list[DamageRow]
    grenades: list[GrenadeRow] = field(default_factory=list)
    selected_ticks: list[SelectedTickRow] = field(default_factory=list)
    event_counts: dict[str, int] = field(default_factory=dict)
    source_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
