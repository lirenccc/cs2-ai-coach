"""Schema / evidence / frame post-validation for AI analysis results."""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from .errors import AiEvidenceValidationError
from .models import CoachIncidentAnalysis


def validate_evidence_references(
    result: CoachIncidentAnalysis,
    *,
    allowed_evidence_ids: set[str],
    allowed_frame_ids: set[str],
) -> list[str]:
    errors: list[str] = []

    for fact in result.facts:
        unknown = set(fact.evidence_ids) - allowed_evidence_ids
        if unknown:
            errors.append(f"fact references unknown evidence ids: {sorted(unknown)}")

    for observation in result.observations:
        unknown = set(observation.frame_ids) - allowed_frame_ids
        if unknown:
            errors.append(f"observation references unknown frame ids: {sorted(unknown)}")

    for inference in result.inferences:
        unknown = set(inference.evidence_ids) - allowed_evidence_ids
        if unknown:
            errors.append(f"inference references unknown evidence ids: {sorted(unknown)}")

    return errors


def parse_analysis_payload(payload: Any) -> CoachIncidentAnalysis:
    """Parse/validate structured output against the Pydantic schema contract."""
    if isinstance(payload, CoachIncidentAnalysis):
        return payload
    if isinstance(payload, str):
        payload = json.loads(payload)
    return CoachIncidentAnalysis.model_validate(payload)


def validate_analysis_result(
    result: CoachIncidentAnalysis | dict[str, Any] | str,
    *,
    allowed_evidence_ids: set[str],
    allowed_frame_ids: set[str],
) -> CoachIncidentAnalysis:
    """
    Full post-validator:

    - JSON/schema shape (Pydantic mirrors coach_incident_analysis.schema.json)
    - confidence / severity ranges
    - evidence_id / frame_id provenance
    """
    try:
        parsed = parse_analysis_payload(result)
    except (ValidationError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise AiEvidenceValidationError(
            "Structured analysis failed schema validation.",
            errors=[str(exc)],
        ) from exc

    ref_errors = validate_evidence_references(
        parsed,
        allowed_evidence_ids=allowed_evidence_ids,
        allowed_frame_ids=allowed_frame_ids,
    )
    if ref_errors:
        raise AiEvidenceValidationError(
            "Structured analysis failed evidence/frame validation.",
            errors=ref_errors,
        )
    return parsed
