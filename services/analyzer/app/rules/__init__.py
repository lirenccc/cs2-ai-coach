"""Deterministic incident rule engine.

Rules consume normalized structured facts only. They never call AiProvider,
capture, NetCon, or UI code.
"""

from .base import Rule, RuleMetadata
from .from_parsed import rule_context_from_parsed
from .models import (
    EvidenceKind,
    IncidentCandidate,
    RuleEvaluationResult,
    RuleEvidence,
    RuleOutcome,
    UnresolvedEvaluation,
)
from .r001_opening_death import OpeningDeathRule
from .r002_untraded_death import UntradedDeathRule
from .r003_advantage_loss import AdvantageLossRule
from .thresholds import RULE_THRESHOLDS_VERSION, RuleThresholds
from .trades import Kill, is_opening_death, is_untraded_death

__all__ = [
    "AdvantageLossRule",
    "EvidenceKind",
    "IncidentCandidate",
    "Kill",
    "OpeningDeathRule",
    "RULE_THRESHOLDS_VERSION",
    "Rule",
    "RuleEvaluationResult",
    "RuleEvidence",
    "RuleMetadata",
    "RuleOutcome",
    "RuleThresholds",
    "UnresolvedEvaluation",
    "UntradedDeathRule",
    "is_opening_death",
    "is_untraded_death",
    "rule_context_from_parsed",
]


def default_rules() -> tuple[Rule, ...]:
    return (OpeningDeathRule(), UntradedDeathRule(), AdvantageLossRule())
