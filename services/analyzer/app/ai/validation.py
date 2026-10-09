from __future__ import annotations

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
