"""AI provider adapters and validation."""

from .errors import (
    AiAuthenticationError,
    AiEvidenceValidationError,
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
from .provider import AiProvider
from .validation import validate_analysis_result, validate_evidence_references
from .versions import AI_CONTRACT_VERSION, SCHEMA_VERSION

__all__ = [
    "AI_CONTRACT_VERSION",
    "SCHEMA_VERSION",
    "AiAuthenticationError",
    "AiEvidenceValidationError",
    "AiIncompleteResponseError",
    "AiNetworkError",
    "AiProvider",
    "AiProviderError",
    "AiProviderServerError",
    "AiRateLimitError",
    "AiRefusalError",
    "AiStructuredOutputError",
    "AiTimeoutError",
    "CoachIncidentAnalysis",
    "compute_request_fingerprint",
    "validate_analysis_result",
    "validate_evidence_references",
]
