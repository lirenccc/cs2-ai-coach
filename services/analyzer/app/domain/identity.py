"""Stable person / demo-local controller / pawn life identities.

These are deliberately separate: one Steam player may have multiple controller
sessions; one controller may own multiple pawn lives; bot takeover must not
corrupt PlayerIdentity.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PlayerIdentity:
    id: str
    steamid64: str | None
    display_name_latest: str | None


@dataclass(frozen=True, slots=True)
class ControllerSession:
    id: str
    match_id: str
    userid: int
    player_identity_id: str | None
    connected_demo_tick: int | None
    disconnected_demo_tick: int | None
    is_bot: bool
    is_hltv: bool


@dataclass(frozen=True, slots=True)
class PawnLife:
    id: str
    match_id: str
    controller_session_id: str | None
    pawn_handle: int
    spawn_demo_tick: int | None
    death_demo_tick: int | None
