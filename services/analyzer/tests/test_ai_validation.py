from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.ai.errors import AiEvidenceValidationError
from app.ai.models import (
    CoachIncidentAnalysis,
    Fact,
    Inference,
    Observation,
    Recommendation,
)
from app.ai.validation import (
    parse_analysis_payload,
    validate_analysis_result,
    validate_evidence_references,
)


def make_result() -> CoachIncidentAnalysis:
    return CoachIncidentAnalysis(
        incident_id="inc-1",
        summary="Candidate repeat peek.",
        severity=3,
        confidence=0.7,
        facts=[Fact(statement="Damage occurred.", evidence_ids=["ev-1"])],
        observations=[Observation(statement="Player is exposed.", frame_ids=["frame-1"])],
        inferences=[
            Inference(
                statement="A second exposure may have increased risk.",
                confidence=0.6,
                evidence_ids=["ev-1"],
            )
        ],
        recommendations=[
            Recommendation(
                priority=1,
                action="Break line of sight.",
                rationale="Avoid a repeated unsupported duel.",
                practice="Review repeat-peek incidents.",
            )
        ],
        uncertainties=[],
    )


def test_valid_references_pass():
    errors = validate_evidence_references(
        make_result(),
        allowed_evidence_ids={"ev-1"},
        allowed_frame_ids={"frame-1"},
    )
    assert errors == []


def test_unknown_fact_and_frame_ids_fail():
    errors = validate_evidence_references(
        make_result(),
        allowed_evidence_ids=set(),
        allowed_frame_ids=set(),
    )
    assert len(errors) == 3
    assert any("unknown evidence" in error for error in errors)
    assert any("unknown frame" in error for error in errors)


def test_unknown_evidence_id_rejected_by_post_validator():
    with pytest.raises(AiEvidenceValidationError) as exc:
        validate_analysis_result(
            make_result(),
            allowed_evidence_ids={"ev-other"},
            allowed_frame_ids={"frame-1"},
        )
    assert exc.value.code == "AI_EVIDENCE_VALIDATION_FAILED"
    assert any("unknown evidence" in err for err in (exc.value.details or {}).get("errors", []))


def test_unknown_frame_id_rejected_by_post_validator():
    with pytest.raises(AiEvidenceValidationError) as exc:
        validate_analysis_result(
            make_result(),
            allowed_evidence_ids={"ev-1"},
            allowed_frame_ids={"frame-other"},
        )
    assert any("unknown frame" in err for err in (exc.value.details or {}).get("errors", []))


def test_invalid_confidence_rejected():
    with pytest.raises(ValidationError):
        CoachIncidentAnalysis(
            incident_id="inc-1",
            summary="x",
            severity=3,
            confidence=1.5,
            facts=[],
            observations=[],
            inferences=[],
            recommendations=[],
            uncertainties=[],
        )


def test_invalid_severity_enum_range_rejected():
    with pytest.raises(ValidationError):
        CoachIncidentAnalysis(
            incident_id="inc-1",
            summary="x",
            severity=9,
            confidence=0.5,
            facts=[],
            observations=[],
            inferences=[],
            recommendations=[],
            uncertainties=[],
        )


def test_missing_required_field_rejected():
    with pytest.raises(ValidationError):
        parse_analysis_payload(
            {
                "incident_id": "inc-1",
                "summary": "x",
                "severity": 3,
                # confidence missing
                "facts": [],
                "observations": [],
                "inferences": [],
                "recommendations": [],
                "uncertainties": [],
            }
        )


def test_malformed_structured_result_rejected():
    with pytest.raises(AiEvidenceValidationError) as exc:
        validate_analysis_result(
            "{not-json",
            allowed_evidence_ids=set(),
            allowed_frame_ids=set(),
        )
    assert exc.value.code == "AI_EVIDENCE_VALIDATION_FAILED"


def test_post_validator_accepts_valid_result():
    parsed = validate_analysis_result(
        make_result(),
        allowed_evidence_ids={"ev-1"},
        allowed_frame_ids={"frame-1"},
    )
    assert parsed.incident_id == "inc-1"
