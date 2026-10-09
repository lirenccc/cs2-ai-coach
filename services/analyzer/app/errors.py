from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class AppError(Exception):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class DemoInvalidError(AppError):
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__("DEMO_INVALID", message, False, details)


class ParserUnavailableError(AppError):
    def __init__(self, message: str = "The configured demo parser is unavailable."):
        super().__init__("PARSER_UNAVAILABLE", message, False)


class ParserCrashError(AppError):
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__("PARSER_CRASH", message, True, details)


class ParserCompatibilityError(AppError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "PARSER_SCHEMA_CHANGED",
        details: dict[str, Any] | None = None,
    ):
        super().__init__(code, message, False, details)


class MissingExpectedEventError(ParserCompatibilityError):
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message,
            code="MISSING_EXPECTED_EVENT",
            details=details,
        )
