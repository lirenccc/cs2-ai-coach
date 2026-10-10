from __future__ import annotations

from pathlib import Path

import pytest

from app.ai.fingerprint import (
    assert_fingerprint_excludes_secrets,
    compute_request_fingerprint,
    fingerprint_payload_from_request,
)
from app.ai.request import FrameEvidence, IncidentAnalysisRequest, StructuredEvidenceFact
from app.ai.versions import AI_CONTRACT_VERSION, SCHEMA_VERSION


def _request(**overrides) -> IncidentAnalysisRequest:
    base = dict(
        incident_id="inc-provider-smoke-a04",
        incident_type="PROVIDER_SMOKE_TEST",
        facts=(
            StructuredEvidenceFact(
                evidence_id="ev-smoke-a04-bomb-exploded",
                event_type="bomb_exploded",
                demo_tick=79639,
                round_id=13,
                statement="bomb exploded",
            ),
        ),
        frames=(
            FrameEvidence(
                frame_id="frame-smoke-a04-0008",
                frame_sha256="e0370b197addc71af40527b54cb2670748c9659971f3bed295e30723299824fa",
                path=Path("C:/private/runtime/captures/match/cap/frame-0008.png"),
                capture_manifest_version="p0.6-2026-10-10",
                evidence_lineage_version="p0.6a-2026-10-10",
                requested_demo_tick=79639,
                replay_calibration_version="p0.5a-2026-10-10",
                geometry_status="client_1280x720_wgc_1282x752_raw_preserved",
                capture_role="event_anchor",
                width=1282,
                height=752,
            ),
        ),
        model="gpt-4o-mini",
        prompt_version="provider_smoke_v001",
        schema_version=SCHEMA_VERSION,
        ai_contract_version=AI_CONTRACT_VERSION,
        provider="openai",
        image_detail="auto",
        store=False,
        analysis_request_id="req-random-should-not-affect-fingerprint",
    )
    base.update(overrides)
    return IncidentAnalysisRequest(**base)


def test_request_fingerprint_is_deterministic():
    a = compute_request_fingerprint(_request())
    b = compute_request_fingerprint(
        _request(analysis_request_id="completely-different-id")
    )
    assert a == b
    assert len(a) == 64


def test_fingerprint_changes_on_model_change():
    base = compute_request_fingerprint(_request())
    changed = compute_request_fingerprint(_request(model="gpt-4o"))
    assert base != changed


def test_fingerprint_changes_on_frame_hash_change():
    frame = _request().frames[0]
    altered = FrameEvidence(
        frame_id=frame.frame_id,
        frame_sha256="0" * 64,
        path=frame.path,
        capture_manifest_version=frame.capture_manifest_version,
        evidence_lineage_version=frame.evidence_lineage_version,
        requested_demo_tick=frame.requested_demo_tick,
        replay_calibration_version=frame.replay_calibration_version,
        geometry_status=frame.geometry_status,
        capture_role=frame.capture_role,
        width=frame.width,
        height=frame.height,
    )
    base = compute_request_fingerprint(_request())
    changed = compute_request_fingerprint(_request(frames=(altered,)))
    assert base != changed


def test_fingerprint_changes_on_evidence_change():
    fact = StructuredEvidenceFact(
        evidence_id="ev-other",
        event_type="bomb_exploded",
        demo_tick=79639,
        round_id=13,
        statement="different evidence",
    )
    base = compute_request_fingerprint(_request())
    changed = compute_request_fingerprint(_request(facts=(fact,)))
    assert base != changed


def test_fingerprint_changes_on_prompt_or_schema_version():
    base = compute_request_fingerprint(_request())
    assert base != compute_request_fingerprint(_request(prompt_version="provider_smoke_v999"))
    assert base != compute_request_fingerprint(_request(schema_version="other.schema"))


def test_fingerprint_excludes_secrets_and_absolute_paths():
    payload = fingerprint_payload_from_request(_request())
    serialized = str(payload).lower()
    assert "api_key" not in serialized
    assert "sk-" not in serialized
    assert "c:/private" not in serialized
    assert "authorization" not in serialized
    assert_fingerprint_excludes_secrets(payload)


def test_fingerprint_rejects_secret_injection():
    payload = fingerprint_payload_from_request(_request())
    payload["api_key"] = "sk-secret"
    with pytest.raises(ValueError):
        assert_fingerprint_excludes_secrets(payload)
