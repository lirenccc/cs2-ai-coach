from __future__ import annotations

from app.ai.models import (
    CoachIncidentAnalysis,
    Fact,
    Inference,
    Observation,
    Recommendation,
)
from app.ai.validation import validate_evidence_references


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
