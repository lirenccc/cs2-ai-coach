"""Versioned evidence lineage and round-side contracts (P0.6A).

Validation / contract-hardening only — does not rewrite parser or Storage v2.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


EVIDENCE_LINEAGE_VERSION = "p0.6a-2026-10-10"
IDENTITY_SEMANTICS_VERSION = "p0.6a-2026-10-10"
ROUND_SIDE_CONTRACT_VERSION = "p0.6a-2026-10-10"


class EvidenceCertainty(str, Enum):
    VERIFIED = "verified"
    DERIVED = "derived"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class EvidenceLineage:
    """Traceable chain from parser context to a captured frame.

    Optional fields stay unset when attribution is genuinely unavailable.
    Display names are never identity keys.
    """

    evidence_lineage_version: str
    match_id: str
    frame_id: str
    frame_sha256: str
    requested_demo_tick: int
    replay_calibration_version: str
    cs2_build_identity: str
    capture_manifest_id: str | None = None
    parser_event_id: str | None = None
    round_id: int | None = None
    player_identity_id: str | None = None
    controller_session_id: str | None = None
    pawn_life_id: str | None = None
    calibrated: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_lineage_version": self.evidence_lineage_version,
            "match_id": self.match_id,
            "parser_event_id": self.parser_event_id,
            "round_id": self.round_id,
            "player_identity_id": self.player_identity_id,
            "controller_session_id": self.controller_session_id,
            "pawn_life_id": self.pawn_life_id,
            "requested_demo_tick": self.requested_demo_tick,
            "replay_calibration_version": self.replay_calibration_version,
            "cs2_build_identity": self.cs2_build_identity,
            "capture_manifest_id": self.capture_manifest_id,
            "frame_id": self.frame_id,
            "frame_sha256": self.frame_sha256,
            "calibrated": self.calibrated,
        }


@dataclass(frozen=True, slots=True)
class RoundPlayerState:
    """Authoritative-enough side/team binding for one identity in one round.

    Consumers must not permanently reuse the initial roster assignment across
    the side transition. Prefer tick/entity `side` / `team_num` at a round tick.
    """

    round_id: int
    player_identity_id: str
    side: str
    team_identity: str | None
    source: str
    contract_version: str = ROUND_SIDE_CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "round_id": self.round_id,
            "player_identity_id": self.player_identity_id,
            "side": self.side,
            "team_identity": self.team_identity,
            "source": self.source,
        }


def assert_lineage_versions(lineage: EvidenceLineage) -> None:
    if lineage.evidence_lineage_version != EVIDENCE_LINEAGE_VERSION:
        raise ValueError(
            f"evidence_lineage_version mismatch: {lineage.evidence_lineage_version}"
        )


def side_from_team_num(team_num: int | float | None) -> str | None:
    """Map entity team_num to side codes (same mapping as team_codes)."""
    if team_num is None:
        return None
    number = int(team_num)
    if number == 2:
        return "t"
    if number == 3:
        return "ct"
    if number == 1:
        return "spectator"
    return None
