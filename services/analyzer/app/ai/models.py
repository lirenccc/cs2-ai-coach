from __future__ import annotations

from pydantic import BaseModel, Field


class Fact(BaseModel):
    statement: str
    evidence_ids: list[str] = Field(min_length=1)


class Observation(BaseModel):
    statement: str
    frame_ids: list[str] = Field(min_length=1)


class Inference(BaseModel):
    statement: str
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str]


class Recommendation(BaseModel):
    priority: int = Field(ge=1, le=5)
    action: str
    rationale: str
    practice: str


class CoachIncidentAnalysis(BaseModel):
    incident_id: str
    summary: str
    severity: int = Field(ge=1, le=5)
    confidence: float = Field(ge=0, le=1)
    facts: list[Fact]
    observations: list[Observation]
    inferences: list[Inference]
    recommendations: list[Recommendation]
    uncertainties: list[str]
