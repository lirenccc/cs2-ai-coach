"""Typed AI provider errors (stable codes for analyzer/clients)."""

from __future__ import annotations

from typing import Any

from ..errors import AppError


class AiProviderError(AppError):
    """Base class for provider / AI pipeline failures."""


class AiAuthenticationError(AiProviderError):
    def __init__(self, message: str = "AI provider authentication failed.", **kwargs: Any):
        super().__init__("AI_AUTH_FAILED", message, False, kwargs or None)


class AiRateLimitError(AiProviderError):
    def __init__(self, message: str = "AI provider rate limit exceeded.", **kwargs: Any):
        super().__init__("AI_RATE_LIMITED", message, True, kwargs or None)


class AiTimeoutError(AiProviderError):
    def __init__(self, message: str = "AI provider request timed out.", **kwargs: Any):
        super().__init__("AI_TIMEOUT", message, True, kwargs or None)


class AiNetworkError(AiProviderError):
    def __init__(self, message: str = "AI provider network failure.", **kwargs: Any):
        super().__init__("AI_NETWORK_FAILED", message, True, kwargs or None)


class AiProviderServerError(AiProviderError):
    def __init__(self, message: str = "AI provider returned a server error.", **kwargs: Any):
        super().__init__("AI_PROVIDER_5XX", message, True, kwargs or None)


class AiRefusalError(AiProviderError):
    def __init__(self, message: str = "AI provider refused the request.", **kwargs: Any):
        super().__init__("AI_REFUSED", message, False, kwargs or None)


class AiIncompleteResponseError(AiProviderError):
    def __init__(self, message: str = "AI provider returned an incomplete response.", **kwargs: Any):
        super().__init__("AI_INCOMPLETE_RESPONSE", message, False, kwargs or None)


class AiStructuredOutputError(AiProviderError):
    def __init__(
        self,
        message: str = "AI provider returned no usable structured output.",
        **kwargs: Any,
    ):
        super().__init__("AI_STRUCTURED_OUTPUT_INVALID", message, False, kwargs or None)


class AiEvidenceValidationError(AiProviderError):
    def __init__(self, message: str, *, errors: list[str] | None = None, **kwargs: Any):
        details = dict(kwargs)
        if errors is not None:
            details["errors"] = errors
        super().__init__("AI_EVIDENCE_VALIDATION_FAILED", message, False, details or None)
