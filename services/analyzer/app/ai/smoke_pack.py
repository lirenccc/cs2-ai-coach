"""Deterministic P0.7 provider smoke evidence pack (not a production incident)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..domain.evidence import EVIDENCE_LINEAGE_VERSION
from .request import FrameEvidence, ImageDetail, IncidentAnalysisRequest, StructuredEvidenceFact
from .versions import (
    AI_CONTRACT_VERSION,
    DEFAULT_IMAGE_DETAIL,
    DEFAULT_PROVIDER_NAME,
    PROVIDER_SMOKE_PROMPT_VERSION,
    SCHEMA_VERSION,
)


# Known P0.6 / P0.6A anchor — bomb exploded after halftime (visual POV may be insufficient).
SMOKE_ANCHOR_ID = "A04_post_halftime_explode"
SMOKE_EVENT_TYPE = "bomb_exploded"
SMOKE_DEMO_TICK = 79639
SMOKE_ROUND_ID = 13
SMOKE_FRAME_HASH = "e0370b197addc71af40527b54cb2670748c9659971f3bed295e30723299824fa"
SMOKE_CAPTURE_MANIFEST_VERSION = "p0.6-2026-10-10"
SMOKE_REPLAY_CALIBRATION_VERSION = "p0.5a-2026-10-10"
SMOKE_GEOMETRY_STATUS = "client_1280x720_wgc_1282x752_raw_preserved"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_provider_smoke_request(
    *,
    frame_path: Path,
    model: str,
    image_detail: ImageDetail = DEFAULT_IMAGE_DETAIL,
    analysis_request_id: str | None = None,
    expect_frame_sha256: str | None = SMOKE_FRAME_HASH,
) -> IncidentAnalysisRequest:
    if not frame_path.is_file():
        raise FileNotFoundError(f"smoke frame not found: {frame_path}")

    digest = _sha256_file(frame_path)
    if expect_frame_sha256 is not None and digest != expect_frame_sha256:
        raise ValueError(
            "smoke frame SHA-256 does not match the known P0.6 A04 capture hash; "
            "pass expect_frame_sha256=None to allow a different local frame"
        )

    evidence = StructuredEvidenceFact(
        evidence_id="ev-smoke-a04-bomb-exploded",
        event_type=SMOKE_EVENT_TYPE,
        demo_tick=SMOKE_DEMO_TICK,
        round_id=SMOKE_ROUND_ID,
        statement=(
            "Parser-derived fact: bomb_exploded at DemoTick "
            f"{SMOKE_DEMO_TICK} in round {SMOKE_ROUND_ID} "
            f"(anchor {SMOKE_ANCHOR_ID})."
        ),
        extras={
            "anchor_id": SMOKE_ANCHOR_ID,
            "semantic_result": "not_visually_observable",
            "certainty": "unresolved",
        },
    )

    frame = FrameEvidence(
        frame_id="frame-smoke-a04-0008",
        frame_sha256=digest,
        path=frame_path,
        capture_manifest_version=SMOKE_CAPTURE_MANIFEST_VERSION,
        evidence_lineage_version=EVIDENCE_LINEAGE_VERSION,
        requested_demo_tick=SMOKE_DEMO_TICK,
        replay_calibration_version=SMOKE_REPLAY_CALIBRATION_VERSION,
        geometry_status=SMOKE_GEOMETRY_STATUS,
        capture_role="event_anchor",
        width=1282,
        height=752,
    )

    return IncidentAnalysisRequest(
        incident_id="inc-provider-smoke-a04",
        incident_type="PROVIDER_SMOKE_TEST",
        facts=(evidence,),
        frames=(frame,),
        model=model,
        prompt_version=PROVIDER_SMOKE_PROMPT_VERSION,
        schema_version=SCHEMA_VERSION,
        ai_contract_version=AI_CONTRACT_VERSION,
        provider=DEFAULT_PROVIDER_NAME,
        image_detail=image_detail,
        store=False,
        analysis_request_id=analysis_request_id,
    )


def redacted_smoke_result_document(
    *,
    request: IncidentAnalysisRequest,
    request_fingerprint: str,
    result: dict,
    validation_ok: bool,
    model_family: str,
    sdk_version: str,
    latency_ms: int | None = None,
) -> dict:
    """Commit-safe redacted representation of a real provider smoke run."""
    return {
        "milestone": "P0.7",
        "provider": request.provider,
        "model_family": model_family,
        "model_configured": request.model,
        "sdk_version": sdk_version,
        "prompt_version": request.prompt_version,
        "schema_version": request.schema_version,
        "ai_contract_version": request.ai_contract_version,
        "image_detail": request.image_detail,
        "store": request.store,
        "request_fingerprint": request_fingerprint,
        "evidence_ids": sorted(request.allowed_evidence_ids()),
        "frame_ids": sorted(request.allowed_frame_ids()),
        "frame_sha256s": sorted(frame.frame_sha256 for frame in request.frames),
        "incident_type": request.incident_type,
        "validation_ok": validation_ok,
        "latency_ms": latency_ms,
        "result": {
            "incident_id": result.get("incident_id"),
            "severity": result.get("severity"),
            "confidence": result.get("confidence"),
            "summary_redacted": _redact_summary(str(result.get("summary") or "")),
            "facts_count": len(result.get("facts") or []),
            "observations_count": len(result.get("observations") or []),
            "inferences_count": len(result.get("inferences") or []),
            "recommendations_count": len(result.get("recommendations") or []),
            "uncertainties_count": len(result.get("uncertainties") or []),
            "fact_evidence_ids": sorted(
                {
                    evidence_id
                    for fact in result.get("facts") or []
                    for evidence_id in fact.get("evidence_ids") or []
                }
            ),
            "observation_frame_ids": sorted(
                {
                    frame_id
                    for obs in result.get("observations") or []
                    for frame_id in obs.get("frame_ids") or []
                }
            ),
        },
        "notes": [
            "Private screenshot bytes are not stored.",
            "Player names / Steam IDs are not included.",
            "Absolute paths are not included.",
        ],
    }


def dumps_redacted(document: dict) -> str:
    return json.dumps(document, indent=2, ensure_ascii=True, sort_keys=True) + "\n"


def _redact_summary(text: str) -> str:
    # Keep shape only; drop free-form model prose that may contain private labels.
    if not text:
        return ""
    return f"<redacted summary length={len(text)}>"
