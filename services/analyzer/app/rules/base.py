"""Rule protocol and metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .context import RuleContext
from .models import RuleEvaluationResult


@dataclass(frozen=True, slots=True)
class RuleMetadata:
    id: str
    version: str
    incident_type: str
    required_inputs: tuple[str, ...]
    default_thresholds: dict[str, int | float]


@runtime_checkable
class Rule(Protocol):
    """Deterministic rule: normalized facts in → candidates / unresolved out."""

    @property
    def metadata(self) -> RuleMetadata: ...

    def evaluate(self, context: RuleContext) -> RuleEvaluationResult: ...
