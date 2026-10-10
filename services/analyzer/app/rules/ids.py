"""Deterministic incident / evidence identity helpers."""

from __future__ import annotations

import hashlib


def stable_hash(payload: str, *, prefix: str, length: int = 16) -> str:
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]
    return f"{prefix}{digest}"


def candidate_id(
    *,
    rule_id: str,
    rule_version: str,
    match_id: str,
    round_id: str,
    subject: str,
    anchor_demo_tick: int,
) -> str:
    """Stable semantic ID — no wall-clock, UUID, path, or AI output."""

    return stable_hash(
        "|".join(
            [
                rule_id,
                rule_version,
                match_id,
                round_id,
                subject,
                str(anchor_demo_tick),
            ]
        ),
        prefix="inc_",
    )


def evidence_id(*parts: str) -> str:
    return stable_hash("|".join(parts), prefix="ev_")
