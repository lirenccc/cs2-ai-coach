"""BOT takeover attribution contract (P0.6A).

Based on observed structural-probe + kill events for the private fixture.
Does not invent identity when attribution is unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .evidence import EvidenceCertainty, IDENTITY_SEMANTICS_VERSION


class AttributionKind(str, Enum):
    KILL = "kill"
    DEATH = "death"
    DAMAGE = "damage"
    SURVIVAL = "survival"
    TRADE_OPPORTUNITY = "trade_opportunity"


@dataclass(frozen=True, slots=True)
class AttributionRule:
    kind: AttributionKind
    credited_to: str
    certainty: EvidenceCertainty
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "credited_to": self.credited_to,
            "certainty": self.certainty.value,
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class TakeoverTimeline:
    """Redacted before/after snapshot around one bot_takeover event."""

    identity_semantics_version: str
    anchor_id: str
    demo_tick: int
    server_tick: int | None
    controller_userid: int
    botid_raw: int | None
    pawn_handle_at_takeover: int | None
    before_controller_userid: int
    before_pawn_handle: int | None
    before_death_demo_tick: int | None
    after_controller_userid: int
    after_pawn_handle: int | None
    after_death_demo_tick: int | None
    credited_identity_token: str | None
    botid_equals_userid: bool
    attribution: tuple[AttributionRule, ...]
    unresolved: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity_semantics_version": self.identity_semantics_version,
            "anchor_id": self.anchor_id,
            "demo_tick": self.demo_tick,
            "server_tick": self.server_tick,
            "controller_userid": self.controller_userid,
            "botid_raw": self.botid_raw,
            "pawn_handle_at_takeover": self.pawn_handle_at_takeover,
            "before": {
                "controller_userid": self.before_controller_userid,
                "pawn_handle": self.before_pawn_handle,
                "death_demo_tick": self.before_death_demo_tick,
            },
            "after": {
                "controller_userid": self.after_controller_userid,
                "pawn_handle": self.after_pawn_handle,
                "death_demo_tick": self.after_death_demo_tick,
                "credited_identity_token": self.credited_identity_token,
            },
            "botid_equals_userid": self.botid_equals_userid,
            "attribution": [a.to_dict() for a in self.attribution],
            "unresolved": list(self.unresolved),
        }


def default_takeover_attribution() -> tuple[AttributionRule, ...]:
    """How later deterministic rules should credit events around takeover.

    VERIFIED from fixture: post-takeover death uses the human controller userid
    and a new pawn_handle. Kills/damage similarly keyed by userid/pawn in events.
    """

    return (
        AttributionRule(
            kind=AttributionKind.DEATH,
            credited_to="controller_session.player_identity_id when known; else controller_session only",
            certainty=EvidenceCertainty.VERIFIED,
            notes="Post-takeover player_death keeps the taking-over controller userid and the takeover pawn_handle",
        ),
        AttributionRule(
            kind=AttributionKind.KILL,
            credited_to="attacker controller_session / player_identity_id at event tick",
            certainty=EvidenceCertainty.DERIVED,
            notes="Kill events expose attacker_userid/pawn; credit the controller active at that tick",
        ),
        AttributionRule(
            kind=AttributionKind.DAMAGE,
            credited_to="attacker/victim controller_session at event tick",
            certainty=EvidenceCertainty.DERIVED,
            notes="Same userid/pawn fields as kills; no separate takeover remap observed",
        ),
        AttributionRule(
            kind=AttributionKind.SURVIVAL,
            credited_to="open pawn_life for controller_session (spawn..death)",
            certainty=EvidenceCertainty.VERIFIED,
            notes="Takeover starts a new pawn_life; prior life ends at pre-takeover death when present",
        ),
        AttributionRule(
            kind=AttributionKind.TRADE_OPPORTUNITY,
            credited_to="UNRESOLVED without round-side + timing policy",
            certainty=EvidenceCertainty.UNRESOLVED,
            notes="Trade windows need side-aware teammates; do not invent from display names",
        ),
    )


def build_a03_takeover_timeline() -> TakeoverTimeline:
    """Frozen redacted timeline for calibration anchor A03 / takeover @ 33717."""

    return TakeoverTimeline(
        identity_semantics_version=IDENTITY_SEMANTICS_VERSION,
        anchor_id="A03_near_bot_death",
        demo_tick=33717,
        server_tick=37496,
        controller_userid=3,
        botid_raw=3,
        pawn_handle_at_takeover=432572463,
        before_controller_userid=3,
        before_pawn_handle=-1370816145,
        before_death_demo_tick=33462,
        after_controller_userid=3,
        after_pawn_handle=432572463,
        after_death_demo_tick=34176,
        credited_identity_token="C3",
        botid_equals_userid=True,
        attribution=default_takeover_attribution(),
        unresolved=(
            "structural-probe botid equals userid on all 12 takeovers in this fixture; "
            "cannot distinguish bot controller id from human without richer entity state",
            "PlayerIdentity steam linkage for C3 not committed in redacted fixtures",
        ),
    )
