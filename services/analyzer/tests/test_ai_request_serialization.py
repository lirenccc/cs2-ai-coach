from __future__ import annotations

import json
from pathlib import Path

from app.ai.openai_provider import build_user_content
from app.ai.privacy import safe_request_log_fields
from app.ai.request import FrameEvidence, IncidentAnalysisRequest, StructuredEvidenceFact
from app.ai.smoke_pack import build_provider_smoke_request
from app.ai.versions import AI_CONTRACT_VERSION, SCHEMA_VERSION


def test_fact_packet_serialization_excludes_secrets_and_paths(tmp_path: Path):
    frame = tmp_path / "frame-0008.png"
    frame.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    request = IncidentAnalysisRequest(
        incident_id="inc-1",
        incident_type="PROVIDER_SMOKE_TEST",
        facts=(
            StructuredEvidenceFact(
                evidence_id="ev-1",
                event_type="bomb_exploded",
                demo_tick=79639,
                round_id=13,
                statement="bomb exploded",
            ),
        ),
        frames=(
            FrameEvidence(
                frame_id="frame-1",
                frame_sha256="ab" * 32,
                path=Path(r"C:\Users\secret\runtime\captures\match\cap\frame-0008.png"),
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
        store=False,
        image_detail="auto",
    )
    packet = request.fact_packet_for_prompt()
    serialized = json.dumps(packet)
    assert "Users\\secret" not in serialized
    assert "api_key" not in serialized
    assert packet["frames"][0]["frame_sha256"] == "ab" * 32
    assert packet["frames"][0]["requested_demo_tick"] == 79639
    assert "path" not in packet["frames"][0]


def test_store_false_on_smoke_pack(tmp_path: Path):
    # Use allow-any-hash path by writing bytes then overriding expect.
    frame = tmp_path / "frame-0008.png"
    frame.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x01" * 64)
    request = build_provider_smoke_request(
        frame_path=frame,
        model="gpt-4o-mini",
        expect_frame_sha256=None,
    )
    assert request.store is False
    assert request.incident_type == "PROVIDER_SMOKE_TEST"
    content = build_user_content(request)
    assert content[1]["detail"] == "auto"


def test_safe_log_fields_exclude_payload_bodies():
    fields = safe_request_log_fields(
        request_fingerprint="f" * 64,
        model="gpt-4o-mini",
        prompt_version="provider_smoke_v001",
        schema_version=SCHEMA_VERSION,
        ai_contract_version=AI_CONTRACT_VERSION,
        evidence_ids=["ev-1"],
        frame_ids=["frame-1"],
        frame_sha256s=["ab" * 32],
        frame_dimensions=[(1282, 752)],
        image_detail="auto",
        store=False,
        validation_ok=True,
        usage={"input_tokens": 1},
    )
    blob = json.dumps(fields)
    assert "base64" not in blob
    assert fields["store"] is False
    assert fields["frame_dimensions"][0]["width"] == 1282
