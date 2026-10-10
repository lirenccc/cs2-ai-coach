"""OpenAI Responses API adapter (Structured Outputs + image input)."""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import time
from pathlib import Path
from typing import Any

from .errors import (
    AiAuthenticationError,
    AiIncompleteResponseError,
    AiNetworkError,
    AiProviderError,
    AiProviderServerError,
    AiRateLimitError,
    AiRefusalError,
    AiStructuredOutputError,
    AiTimeoutError,
)
from .fingerprint import compute_request_fingerprint
from .models import CoachIncidentAnalysis
from .privacy import redact_path_for_logs, safe_request_log_fields
from .prompt_loader import load_prompt
from .request import FrameEvidence, ImageDetail, IncidentAnalysisRequest
from .validation import validate_analysis_result
from .versions import (
    AI_CONTRACT_VERSION,
    DEFAULT_IMAGE_DETAIL,
    DEFAULT_PROVIDER_NAME,
    PROVIDER_SMOKE_PROMPT_VERSION,
    SCHEMA_VERSION,
)

logger = logging.getLogger(__name__)


def _data_url(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    mime = mime or "image/jpeg"
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{payload}"


def build_image_content(frame: FrameEvidence, *, image_detail: ImageDetail) -> dict[str, object]:
    """Bounded image input for Responses API (detail explicit; no geometry rewrite)."""
    return {
        "type": "input_image",
        "image_url": _data_url(frame.path),
        "detail": image_detail,
    }


def build_user_content(
    request: IncidentAnalysisRequest,
) -> list[dict[str, object]]:
    packet = request.fact_packet_for_prompt()
    content: list[dict[str, object]] = [
        {
            "type": "input_text",
            "text": (
                "Analyze this offline CS2 Demo incident packet.\n"
                f"fact_packet={json.dumps(packet, ensure_ascii=True, sort_keys=True)}"
            ),
        }
    ]
    for frame in request.frames:
        content.append(build_image_content(frame, image_detail=request.image_detail))
    return content


def map_openai_exception(exc: BaseException) -> AiProviderError:
    """Map SDK / transport failures to typed analyzer errors."""
    try:
        from openai import (
            APIConnectionError,
            APITimeoutError,
            AuthenticationError,
            InternalServerError,
            LengthFinishReasonError,
            RateLimitError,
            APIStatusError,
        )
    except ImportError:
        return AiProviderError("AI_PROVIDER_ERROR", str(exc), False)

    if isinstance(exc, AuthenticationError):
        return AiAuthenticationError(str(exc) or "AI provider authentication failed.")
    if isinstance(exc, RateLimitError):
        return AiRateLimitError(str(exc) or "AI provider rate limit exceeded.")
    if isinstance(exc, APITimeoutError):
        return AiTimeoutError(str(exc) or "AI provider request timed out.")
    if isinstance(exc, APIConnectionError):
        return AiNetworkError(str(exc) or "AI provider network failure.")
    if isinstance(exc, InternalServerError):
        return AiProviderServerError(str(exc) or "AI provider returned a server error.")
    if isinstance(exc, LengthFinishReasonError):
        return AiIncompleteResponseError(str(exc) or "AI provider hit length limit.")
    if isinstance(exc, APIStatusError):
        status = getattr(exc, "status_code", None)
        if status in {401, 403}:
            return AiAuthenticationError(str(exc), status_code=status)
        if status == 429:
            return AiRateLimitError(str(exc), status_code=status)
        if status is not None and status >= 500:
            return AiProviderServerError(str(exc), status_code=status)
        return AiProviderError("AI_PROVIDER_HTTP_ERROR", str(exc), False, {"status_code": status})
    if isinstance(exc, AiProviderError):
        return exc
    return AiProviderError("AI_PROVIDER_ERROR", str(exc), False)


class OpenAiProvider:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_s: float = 60.0,
        default_prompt_version: str = PROVIDER_SMOKE_PROMPT_VERSION,
        default_image_detail: ImageDetail = DEFAULT_IMAGE_DETAIL,
        store: bool = False,
        base_url: str | None = None,
    ):
        if not api_key:
            raise ValueError("api_key is required")
        if not model:
            raise ValueError("model is required")

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "OpenAI SDK is not installed. Install analyzer with the [ai] extra."
            ) from exc

        client_kwargs: dict[str, Any] = {"api_key": api_key, "timeout": timeout_s}
        if base_url:
            client_kwargs["base_url"] = base_url
        self.client = OpenAI(**client_kwargs)
        self.model = model
        self.timeout_s = timeout_s
        self.default_prompt_version = default_prompt_version
        self.default_image_detail = default_image_detail
        self.store = store
        self.base_url = base_url
        self.provider_name = DEFAULT_PROVIDER_NAME

    def analyze_incident(
        self,
        *,
        incident_id: str,
        fact_packet_json: str,
        image_paths: list[Path],
    ) -> CoachIncidentAnalysis:
        """Backward-compatible entry (no evidence post-validation; caller validates)."""
        prompt_text, _prompt_hash = load_prompt(self.default_prompt_version)
        content: list[dict[str, object]] = [
            {
                "type": "input_text",
                "text": (
                    "Analyze this offline CS2 Demo incident. "
                    "Treat supplied demo facts as authoritative. "
                    "Do not invent game facts. If evidence is insufficient, "
                    "state uncertainty.\n\n"
                    f"incident_id={incident_id}\n"
                    f"fact_packet={fact_packet_json}"
                ),
            }
        ]
        for path in image_paths:
            content.append(
                {
                    "type": "input_image",
                    "image_url": _data_url(path),
                    "detail": self.default_image_detail,
                }
            )

        try:
            response = self.client.responses.parse(
                model=self.model,
                store=self.store,
                input=[
                    {"role": "system", "content": prompt_text},
                    {"role": "user", "content": content},
                ],
                text_format=CoachIncidentAnalysis,
            )
        except Exception as exc:  # noqa: BLE001
            raise map_openai_exception(exc) from exc

        refusal = _extract_refusal(response)
        if refusal:
            raise AiRefusalError(refusal)
        if getattr(response, "status", None) == "incomplete":
            raise AiIncompleteResponseError("AI provider returned an incomplete response.")

        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise AiStructuredOutputError("Model returned no structured result.")
        if isinstance(parsed, CoachIncidentAnalysis):
            return parsed
        return CoachIncidentAnalysis.model_validate(parsed)

    def analyze_request(
        self,
        request: IncidentAnalysisRequest,
        *,
        post_validate: bool = True,
    ) -> CoachIncidentAnalysis:
        if request.model != self.model:
            # Model remains configuration — honor per-request model without hard-coding.
            pass

        prompt_text, prompt_hash = load_prompt(request.prompt_version)
        fingerprint = compute_request_fingerprint(request)
        started = time.perf_counter()
        usage: dict[str, Any] | None = None

        content = build_user_content(request)
        model_name = request.model or self.model

        log_fields = safe_request_log_fields(
            request_fingerprint=fingerprint,
            model=model_name,
            prompt_version=request.prompt_version,
            schema_version=request.schema_version,
            ai_contract_version=request.ai_contract_version,
            evidence_ids=sorted(request.allowed_evidence_ids()),
            frame_ids=sorted(request.allowed_frame_ids()),
            frame_sha256s=sorted(frame.frame_sha256 for frame in request.frames),
            frame_dimensions=[(frame.width, frame.height) for frame in request.frames],
            image_detail=request.image_detail,
            store=request.store,
        )
        logger.info(
            "ai_request_start frames=%s prompt_hash=%s",
            [redact_path_for_logs(frame.path) for frame in request.frames],
            prompt_hash,
            extra={"ai": log_fields},
        )

        try:
            response = self.client.responses.parse(
                model=model_name,
                store=request.store,
                input=[
                    {"role": "system", "content": prompt_text},
                    {"role": "user", "content": content},
                ],
                text_format=CoachIncidentAnalysis,
            )
        except Exception as exc:  # noqa: BLE001 — mapped to typed errors
            mapped = map_openai_exception(exc)
            logger.info(
                "ai_request_failed code=%s",
                mapped.code,
                extra={
                    "ai": {
                        **log_fields,
                        "latency_ms": int((time.perf_counter() - started) * 1000),
                        "error_code": mapped.code,
                    }
                },
            )
            raise mapped from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        usage = _usage_dict(response)

        status = getattr(response, "status", None)
        if status == "incomplete":
            raise AiIncompleteResponseError(
                "AI provider returned an incomplete response.",
                incomplete_details=str(getattr(response, "incomplete_details", None)),
            )

        refusal = _extract_refusal(response)
        if refusal:
            raise AiRefusalError(refusal)

        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise AiStructuredOutputError("Model returned no structured result.")

        if not isinstance(parsed, CoachIncidentAnalysis):
            parsed = CoachIncidentAnalysis.model_validate(parsed)

        if post_validate:
            parsed = validate_analysis_result(
                parsed,
                allowed_evidence_ids=request.allowed_evidence_ids(),
                allowed_frame_ids=request.allowed_frame_ids(),
            )

        logger.info(
            "ai_request_ok",
            extra={
                "ai": {
                    **log_fields,
                    "latency_ms": latency_ms,
                    "validation_ok": True,
                    "usage": usage,
                }
            },
        )
        return parsed


def _usage_dict(response: Any) -> dict[str, Any] | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    if hasattr(usage, "model_dump"):
        return usage.model_dump()
    if isinstance(usage, dict):
        return usage
    return {"raw": str(usage)}


def _extract_refusal(response: Any) -> str | None:
    output = getattr(response, "output", None) or []
    for item in output:
        content = getattr(item, "content", None) or []
        for part in content:
            refusal = getattr(part, "refusal", None)
            if refusal:
                return str(refusal)
            part_type = getattr(part, "type", None)
            if part_type == "refusal":
                return str(getattr(part, "refusal", None) or getattr(part, "text", None) or "refused")
    return None
