from __future__ import annotations

import base64
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.ai.errors import (
    AiAuthenticationError,
    AiIncompleteResponseError,
    AiNetworkError,
    AiProviderServerError,
    AiRateLimitError,
    AiRefusalError,
    AiTimeoutError,
)
from app.ai.models import CoachIncidentAnalysis, Fact, Observation
from app.ai.openai_provider import (
    OpenAiProvider,
    build_image_content,
    build_user_content,
    map_openai_exception,
)
from app.ai.privacy import redact_path_for_logs, sanitize_log_text
from app.ai.prompt_loader import load_prompt
from app.ai.request import FrameEvidence, IncidentAnalysisRequest, StructuredEvidenceFact
from app.ai.versions import (
    AI_CONTRACT_VERSION,
    PROVIDER_SMOKE_PROMPT_VERSION,
    SCHEMA_VERSION,
)


def _png(tmp_path: Path) -> Path:
    # Minimal valid-ish PNG header bytes are enough for data-url construction tests.
    path = tmp_path / "frame-0008.png"
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    )
    return path


def _request(frame_path: Path, **overrides) -> IncidentAnalysisRequest:
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
                frame_sha256="a" * 64,
                path=frame_path,
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
        prompt_version=PROVIDER_SMOKE_PROMPT_VERSION,
        schema_version=SCHEMA_VERSION,
        ai_contract_version=AI_CONTRACT_VERSION,
        provider="openai",
        image_detail="auto",
        store=False,
    )
    base.update(overrides)
    return IncidentAnalysisRequest(**base)


def test_prompt_version_is_loaded_from_file_not_inline_only():
    text, digest = load_prompt(PROVIDER_SMOKE_PROMPT_VERSION)
    assert "authoritative" in text.lower()
    assert "evidence_id" in text
    assert "frame_id" in text
    assert len(digest) == 64


def test_image_content_construction_and_detail(tmp_path: Path):
    frame_path = _png(tmp_path)
    request = _request(frame_path, image_detail="high")
    content = build_user_content(request)
    assert content[0]["type"] == "input_text"
    assert "ev-smoke-a04-bomb-exploded" in content[0]["text"]
    image = content[1]
    assert image["type"] == "input_image"
    assert image["detail"] == "high"
    assert str(image["image_url"]).startswith("data:image/png;base64,")
    # Ensure bytes were encoded (and tests never log them).
    raw = base64.b64decode(str(image["image_url"]).split(",", 1)[1])
    assert raw.startswith(b"\x89PNG")


def test_build_image_content_keeps_explicit_detail(tmp_path: Path):
    frame = _request(_png(tmp_path)).frames[0]
    payload = build_image_content(frame, image_detail="low")
    assert payload["detail"] == "low"


def test_store_false_and_model_configurable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    captured: dict = {}

    class FakeParsed:
        output_parsed = CoachIncidentAnalysis(
            incident_id="inc-provider-smoke-a04",
            summary="Smoke ok.",
            severity=1,
            confidence=0.4,
            facts=[Fact(statement="bomb exploded", evidence_ids=["ev-smoke-a04-bomb-exploded"])],
            observations=[
                Observation(
                    statement="Scene not clearly identifiable.",
                    frame_ids=["frame-smoke-a04-0008"],
                )
            ],
            inferences=[],
            recommendations=[],
            uncertainties=["visual evidence insufficient"],
        )
        status = "completed"
        output = []
        usage = {"input_tokens": 10, "output_tokens": 5}

    class FakeResponses:
        def parse(self, **kwargs):
            captured.update(kwargs)
            return FakeParsed()

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.responses = FakeResponses()

    monkeypatch.setattr("openai.OpenAI", FakeClient)

    provider = OpenAiProvider(api_key="sk-test-key-not-real", model="gpt-4o-mini", store=False)
    # Model remains configuration — override per request.
    result = provider.analyze_request(_request(_png(tmp_path), model="gpt-4o"))
    assert captured["model"] == "gpt-4o"
    assert captured["store"] is False
    assert captured["text_format"] is CoachIncidentAnalysis
    assert result.incident_id == "inc-provider-smoke-a04"


def test_structured_schema_attachment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    captured: dict = {}

    class FakeParsed:
        output_parsed = CoachIncidentAnalysis(
            incident_id="inc-provider-smoke-a04",
            summary="ok",
            severity=1,
            confidence=0.2,
            facts=[Fact(statement="x", evidence_ids=["ev-smoke-a04-bomb-exploded"])],
            observations=[],
            inferences=[],
            recommendations=[],
            uncertainties=["insufficient"],
        )
        status = "completed"
        output = []
        usage = None

    class FakeResponses:
        def parse(self, **kwargs):
            captured.update(kwargs)
            return FakeParsed()

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.responses = FakeResponses()

    monkeypatch.setattr("openai.OpenAI", FakeClient)
    OpenAiProvider(api_key="sk-test", model="gpt-4o-mini").analyze_request(
        _request(_png(tmp_path))
    )
    assert captured["text_format"] is CoachIncidentAnalysis
    system = captured["input"][0]["content"]
    assert "authoritative" in system.lower()


def _httpx_response(status_code: int):
    import httpx

    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    return httpx.Response(status_code, request=request)


def test_refusal_mapping():
    from openai import (
        APIConnectionError,
        APITimeoutError,
        AuthenticationError,
        InternalServerError,
        RateLimitError,
    )

    auth = AuthenticationError("bad key", response=_httpx_response(401), body=None)
    rate = RateLimitError("slow down", response=_httpx_response(429), body=None)
    timeout = APITimeoutError(request=_httpx_response(408).request)
    network = APIConnectionError(message="net", request=_httpx_response(0).request)
    server = InternalServerError("boom", response=_httpx_response(503), body=None)

    assert isinstance(map_openai_exception(auth), AiAuthenticationError)
    assert isinstance(map_openai_exception(rate), AiRateLimitError)
    assert isinstance(map_openai_exception(timeout), AiTimeoutError)
    assert isinstance(map_openai_exception(network), AiNetworkError)
    assert isinstance(map_openai_exception(server), AiProviderServerError)


def test_refusal_and_incomplete_from_response(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    class RefusalParsed:
        output_parsed = None
        status = "completed"
        output = [
            SimpleNamespace(
                content=[SimpleNamespace(type="refusal", refusal="I cannot help with that.")]
            )
        ]
        usage = None

    class IncompleteParsed:
        output_parsed = None
        status = "incomplete"
        incomplete_details = {"reason": "max_output_tokens"}
        output = []
        usage = None

    calls = {"n": 0}

    class FakeResponses:
        def parse(self, **kwargs):
            calls["n"] += 1
            return RefusalParsed() if calls["n"] == 1 else IncompleteParsed()

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.responses = FakeResponses()

    monkeypatch.setattr("openai.OpenAI", FakeClient)
    provider = OpenAiProvider(api_key="sk-test", model="gpt-4o-mini")
    with pytest.raises(AiRefusalError):
        provider.analyze_request(_request(_png(tmp_path)), post_validate=False)
    with pytest.raises(AiIncompleteResponseError):
        provider.analyze_request(_request(_png(tmp_path)), post_validate=False)


def test_timeout_rate_limit_5xx_mapping_from_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    from openai import APITimeoutError, InternalServerError, RateLimitError

    class FakeResponses:
        def __init__(self, exc):
            self.exc = exc

        def parse(self, **kwargs):
            raise self.exc

    monkeypatch.setattr(
        "openai.OpenAI",
        lambda *a, **k: SimpleNamespace(
            responses=FakeResponses(APITimeoutError(request=_httpx_response(408).request))
        ),
    )
    provider = OpenAiProvider(api_key="sk-test", model="gpt-4o-mini")
    with pytest.raises(AiTimeoutError):
        provider.analyze_request(_request(_png(tmp_path)))

    provider.client.responses = FakeResponses(
        RateLimitError("r", response=_httpx_response(429), body=None)
    )
    with pytest.raises(AiRateLimitError):
        provider.analyze_request(_request(_png(tmp_path)))

    provider.client.responses = FakeResponses(
        InternalServerError("s", response=_httpx_response(502), body=None)
    )
    with pytest.raises(AiProviderServerError):
        provider.analyze_request(_request(_png(tmp_path)))


def test_private_path_redaction():
    redacted = redact_path_for_logs(
        Path(r"C:\Users\alice\private\runtime\captures\9208210907649202700_0\cap\frame-0008.png")
    )
    assert "alice" not in redacted
    assert "9208210907649202700_0" not in redacted or redacted.startswith("<redacted>/")
    assert "frame-0008.png" in redacted

    text = sanitize_log_text(
        "key=sk-abcdefghijklmnopqrstuvwxyz path=C:\\Users\\bob\\demo.dem "
        "img=data:image/png;base64,AAAA steam=76561198000000000"
    )
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in text
    assert "AAAA" not in text
    assert "76561198000000000" not in text
    assert "C:\\Users\\bob" not in text
