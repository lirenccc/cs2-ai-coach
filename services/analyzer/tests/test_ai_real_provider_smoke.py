"""Opt-in real OpenAI provider smoke (P0.7). Not for normal CI."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.ai.fingerprint import compute_request_fingerprint
from app.ai.openai_provider import OpenAiProvider
from app.ai.smoke_pack import (
    SMOKE_FRAME_HASH,
    build_provider_smoke_request,
    dumps_redacted,
    redacted_smoke_result_document,
)
from app.ai.validation import validate_analysis_result


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _resolve_api_key() -> str | None:
    return (
        os.environ.get("CS2_COACH_OPENAI_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or None
    )


def _resolve_base_url() -> str | None:
    raw = (
        os.environ.get("CS2_COACH_OPENAI_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or ""
    ).strip()
    return raw or None


def _resolve_frame_path() -> Path | None:
    raw = os.environ.get("CS2_COACH_AI_SMOKE_FRAME", "").strip()
    if not raw:
        return None
    return Path(raw)


def _smoke_ready() -> bool:
    return (
        _env_truthy("CS2_COACH_AI_REAL_SMOKE")
        and bool(_resolve_api_key())
        and bool(_resolve_frame_path())
        and _resolve_frame_path().is_file()  # type: ignore[union-attr]
    )


@pytest.mark.skipif(
    not _smoke_ready(),
    reason=(
        "opt-in real provider smoke: set CS2_COACH_AI_REAL_SMOKE=1, "
        "CS2_COACH_OPENAI_API_KEY (or OPENAI_API_KEY), and "
        "CS2_COACH_AI_SMOKE_FRAME=<private local capture png>"
    ),
)
def test_real_openai_provider_smoke_with_p06_frame() -> None:
    """
    One real Responses API call:

    structured evidence + P0.6 capture frame
      → OpenAiProvider (store=false, structured outputs)
      → schema + evidence/frame post-validation
    """
    api_key = _resolve_api_key()
    frame_path = _resolve_frame_path()
    assert api_key and frame_path

    model = os.environ.get("CS2_COACH_AI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    image_detail = os.environ.get("CS2_COACH_AI_IMAGE_DETAIL", "auto").strip() or "auto"
    if image_detail not in {"auto", "low", "high"}:
        raise AssertionError(f"unsupported image detail: {image_detail}")

    # Allow alternate local frames when explicitly requested.
    expect_hash = None if _env_truthy("CS2_COACH_AI_SMOKE_ALLOW_ANY_FRAME") else SMOKE_FRAME_HASH

    request = build_provider_smoke_request(
        frame_path=frame_path,
        model=model,
        image_detail=image_detail,  # type: ignore[arg-type]
        expect_frame_sha256=expect_hash,
    )
    assert request.store is False
    fingerprint = compute_request_fingerprint(request)

    provider = OpenAiProvider(
        api_key=api_key,
        model=model,
        store=False,
        default_image_detail=image_detail,  # type: ignore[arg-type]
        timeout_s=90.0,
        base_url=_resolve_base_url(),
    )

    result = provider.analyze_request(request, post_validate=True)

    # Structured Outputs prove shape; provenance must still pass our validator.
    validated = validate_analysis_result(
        result,
        allowed_evidence_ids=request.allowed_evidence_ids(),
        allowed_frame_ids=request.allowed_frame_ids(),
    )
    assert validated.incident_id
    assert 0.0 <= validated.confidence <= 1.0

    import openai

    document = redacted_smoke_result_document(
        request=request,
        request_fingerprint=fingerprint,
        result=validated.model_dump(),
        validation_ok=True,
        model_family="openai",
        sdk_version=openai.__version__,
    )

    # Never treat a skip as success — this path only runs when opted in.
    assert document["store"] is False
    assert document["validation_ok"] is True
    assert document["request_fingerprint"] == fingerprint

    if _env_truthy("CS2_COACH_AI_SMOKE_WRITE_FIXTURE"):
        out = (
            Path(__file__).resolve().parents[3]
            / "docs"
            / "spikes"
            / "ai"
            / "fixtures"
            / "provider_smoke_result.redacted.json"
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(dumps_redacted(document), encoding="utf-8")
