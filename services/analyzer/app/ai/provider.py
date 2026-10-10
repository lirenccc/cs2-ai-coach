from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .models import CoachIncidentAnalysis
from .request import IncidentAnalysisRequest


class AiProvider(Protocol):
    def analyze_incident(
        self,
        *,
        incident_id: str,
        fact_packet_json: str,
        image_paths: list[Path],
    ) -> CoachIncidentAnalysis: ...

    def analyze_request(
        self,
        request: IncidentAnalysisRequest,
        *,
        post_validate: bool = True,
    ) -> CoachIncidentAnalysis: ...
