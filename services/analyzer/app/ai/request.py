"""Provider-agnostic incident analysis request shapes."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


ImageDetail = Literal["auto", "low", "high"]


@dataclass(frozen=True, slots=True)
class StructuredEvidenceFact:
    evidence_id: str
    event_type: str
    demo_tick: int
    statement: str
    round_id: int | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def to_normalized_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "evidence_id": self.evidence_id,
            "event_type": self.event_type,
            "demo_tick": self.demo_tick,
            "statement": self.statement,
            "round_id": self.round_id,
        }
        if self.extras:
            payload["extras"] = dict(sorted(self.extras.items(), key=lambda item: item[0]))
        return payload


@dataclass(frozen=True, slots=True)
class FrameEvidence:
    frame_id: str
    frame_sha256: str
    path: Path
    capture_manifest_version: str
    evidence_lineage_version: str
    requested_demo_tick: int
    replay_calibration_version: str
    geometry_status: str
    capture_role: str
    width: int | None = None
    height: int | None = None

    def to_fingerprint_dict(self) -> dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "frame_sha256": self.frame_sha256,
            "capture_manifest_version": self.capture_manifest_version,
            "evidence_lineage_version": self.evidence_lineage_version,
            "requested_demo_tick": self.requested_demo_tick,
            "replay_calibration_version": self.replay_calibration_version,
            "geometry_status": self.geometry_status,
            "capture_role": self.capture_role,
            "width": self.width,
            "height": self.height,
        }

    def to_prompt_metadata(self) -> dict[str, Any]:
        """Lineage facts for the model — no absolute paths."""
        return self.to_fingerprint_dict()


@dataclass(frozen=True, slots=True)
class IncidentAnalysisRequest:
    """Logical request consumed by AiProvider adapters."""

    incident_id: str
    incident_type: str
    facts: tuple[StructuredEvidenceFact, ...]
    frames: tuple[FrameEvidence, ...]
    model: str
    prompt_version: str
    schema_version: str
    ai_contract_version: str
    provider: str = "openai"
    image_detail: ImageDetail = "auto"
    store: bool = False
    analysis_request_id: str | None = None

    def allowed_evidence_ids(self) -> set[str]:
        return {fact.evidence_id for fact in self.facts}

    def allowed_frame_ids(self) -> set[str]:
        return {frame.frame_id for frame in self.frames}

    def fact_packet_for_prompt(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "incident_type": self.incident_type,
            "constraints": [
                "Structured facts are authoritative; do not invent events.",
                "Separate structured facts from visual observations.",
                "Visual claims must reference frame_id.",
                "Factual claims must reference evidence_id.",
                "Uncertainty is allowed when visual evidence is insufficient.",
                "Do not invent unseen players, enemies, or utility.",
                "Do not infer identity from display text.",
            ],
            "facts": [fact.to_normalized_dict() for fact in self.facts],
            "frames": [frame.to_prompt_metadata() for frame in self.frames],
            "versions": {
                "prompt_version": self.prompt_version,
                "schema_version": self.schema_version,
                "ai_contract_version": self.ai_contract_version,
            },
        }
