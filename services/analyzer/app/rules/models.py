"""Deterministic rule-engine result types.

AI must never decide whether a rule fires; these structures are structured facts
and derived metrics only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


RULE_ENGINE_CONTRACT_VERSION = "rule-engine-v1-2026-10-10"


class RuleOutcome(str, Enum):
    """Per-subject evaluation outcome (round / focus / side)."""

    MATCHED = "matched"
    NOT_MATCHED = "not_matched"
    UNRESOLVED = "unresolved"


class EvidenceKind(str, Enum):
    DEMO_EVENT = "demo_event"
    METRIC = "metric"
    ROUND_STATE = "round_state"
    IDENTITY = "identity"


@dataclass(frozen=True, slots=True)
class RuleEvidence:
    """Structured evidence reference — not opaque prose."""

    evidence_id: str
    kind: EvidenceKind
    label: str
    demo_tick: int | None = None
    ref: str | None = None
    name: str | None = None
    value: Any = None
    unit: str | None = None
    certainty: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "evidence_id": self.evidence_id,
            "kind": self.kind.value,
            "label": self.label,
        }
        if self.demo_tick is not None:
            payload["demo_tick"] = self.demo_tick
        if self.ref is not None:
            payload["ref"] = self.ref
        if self.name is not None:
            payload["name"] = self.name
        if self.value is not None:
            payload["value"] = self.value
        if self.unit is not None:
            payload["unit"] = self.unit
        if self.certainty is not None:
            payload["certainty"] = self.certainty
        return payload


@dataclass(frozen=True, slots=True)
class IncidentCandidate:
    """Deterministic incident hypothesis emitted by a rule."""

    id: str
    rule_id: str
    rule_version: str
    incident_type: str
    match_id: str
    round_id: str
    round_no: int
    focus_player_id: str | None
    focus_side: str | None
    start_demo_tick: int
    anchor_demo_tick: int
    end_demo_tick: int
    severity: int
    confidence: float
    metrics: dict[str, Any] = field(default_factory=dict)
    evidence: tuple[RuleEvidence, ...] = ()
    capture_hint: dict[str, Any] = field(default_factory=dict)
    status: str = "candidate"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "incident_type": self.incident_type,
            "match_id": self.match_id,
            "round_id": self.round_id,
            "round_no": self.round_no,
            "focus_player_id": self.focus_player_id,
            "focus_side": self.focus_side,
            "start_demo_tick": self.start_demo_tick,
            "anchor_demo_tick": self.anchor_demo_tick,
            "end_demo_tick": self.end_demo_tick,
            "severity": self.severity,
            "confidence": self.confidence,
            "metrics": dict(self.metrics),
            "evidence": [item.to_dict() for item in self.evidence],
            "capture_hint": dict(self.capture_hint),
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class UnresolvedEvaluation:
    """Explicit insufficient-evidence record — not a silent false negative."""

    rule_id: str
    round_id: str
    round_no: int
    subject: str
    reason: str
    certainty: str = "unresolved"

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "round_id": self.round_id,
            "round_no": self.round_no,
            "subject": self.subject,
            "reason": self.reason,
            "certainty": self.certainty,
        }


@dataclass(frozen=True, slots=True)
class RuleEvaluationResult:
    """Aggregate rule output for a match context.

    Candidates may exist alongside unresolved subjects: uncertainty in one round
    must not invalidate resolved rounds.
    """

    rule_id: str
    rule_version: str
    candidates: tuple[IncidentCandidate, ...]
    unresolved: tuple[UnresolvedEvaluation, ...] = ()

    @property
    def outcome(self) -> RuleOutcome:
        if self.candidates:
            return RuleOutcome.MATCHED
        if self.unresolved:
            return RuleOutcome.UNRESOLVED
        return RuleOutcome.NOT_MATCHED

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "outcome": self.outcome.value,
            "candidates": [c.to_dict() for c in self.candidates],
            "unresolved": [u.to_dict() for u in self.unresolved],
        }
