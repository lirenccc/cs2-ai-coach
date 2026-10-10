"""Deterministic request fingerprint for AI analysis requests."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .request import IncidentAnalysisRequest


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def fingerprint_payload_from_request(request: IncidentAnalysisRequest) -> dict[str, Any]:
    """Build the logical fingerprint document (no secrets / paths / request ids)."""
    return {
        "provider": request.provider,
        "model": request.model,
        "prompt_version": request.prompt_version,
        "schema_version": request.schema_version,
        "ai_contract_version": request.ai_contract_version,
        "image_detail": request.image_detail,
        "incident_type": request.incident_type,
        "incident_id": request.incident_id,
        "facts": [fact.to_normalized_dict() for fact in request.facts],
        "evidence_ids": sorted(request.allowed_evidence_ids()),
        "frames": [frame.to_fingerprint_dict() for frame in request.frames],
        "frame_ids": sorted(request.allowed_frame_ids()),
        "frame_sha256s": sorted(frame.frame_sha256 for frame in request.frames),
    }


def compute_request_fingerprint(request: IncidentAnalysisRequest) -> str:
    payload = fingerprint_payload_from_request(request)
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return digest


def assert_fingerprint_excludes_secrets(payload: dict[str, Any]) -> None:
    """Raise if an obvious secret/path field appears in the fingerprint document."""
    forbidden_substrings = (
        "api_key",
        "authorization",
        "bearer ",
        "sk-",
        "password",
        "token",
    )
    serialized = _canonical_json(payload).lower()
    for needle in forbidden_substrings:
        if needle in serialized:
            raise ValueError(f"fingerprint payload contains forbidden material: {needle}")

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                key_l = str(key).lower()
                if key_l in {"path", "image_url", "absolute_path", "api_key", "authorization"}:
                    raise ValueError(f"fingerprint payload includes forbidden key: {key}")
                if isinstance(value, str) and (
                    ":\\" in value or value.startswith("/") and "runtime" in value
                ):
                    raise ValueError("fingerprint payload includes absolute path-like value")
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
