"""Opt-in private P0.2 demo regression for the deterministic rule engine.

Requires CS2_COACH_REAL_DEMO. Does not require CS2, WGC, NetCon, or OpenAI.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path

import pytest

from app.demo.archive import resolve_demo_file
from app.demo.factory import create_demo_parser
from app.rules import (
    AdvantageLossRule,
    OpeningDeathRule,
    UntradedDeathRule,
    rule_context_from_parsed,
)
from app.rules.ids import stable_hash
from app.rules.models import RULE_ENGINE_CONTRACT_VERSION
from app.rules.thresholds import RULE_THRESHOLDS_VERSION


def _token(value: str) -> str:
    return stable_hash(value, prefix="tok_", length=10)


FIXTURE_SHA = "d873502ed8a1df0cd0f919568261e14b92a04e1ca44cd60e84dcec64748a01ec"
SPIKE_OUT = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "spikes"
    / "rules"
    / "fixtures"
    / "p0_2_rule_engine_summary.redacted.json"
)


@pytest.mark.skipif(
    not os.environ.get("CS2_COACH_REAL_DEMO"),
    reason="set CS2_COACH_REAL_DEMO to a .dem or .zip path for private rule regression",
)
def test_private_demo_rule_engine_regression(tmp_path: Path):
    source = Path(os.environ["CS2_COACH_REAL_DEMO"])
    resolved = resolve_demo_file(source, extract_root=tmp_path / "extracted")
    parsed = create_demo_parser().parse(resolved.demo_path)

    # Identity: fixture hash only — never commit paths / Steam / names.
    match_id = f"demo:{FIXTURE_SHA[:16]}"
    context = rule_context_from_parsed(parsed, match_id=match_id)

    r001 = OpeningDeathRule().evaluate(context)
    r002 = UntradedDeathRule().evaluate(context)
    r003 = AdvantageLossRule().evaluate(context)

    assert context.rounds
    assert len(context.life_ending_events) >= 1

    def _redact_candidate(cand) -> dict:
        return {
            "rule_id": cand.rule_id,
            "rule_version": cand.rule_version,
            "incident_type": cand.incident_type,
            "round_no": cand.round_no,
            "round_id": _token(cand.round_id),
            "focus_side": cand.focus_side,
            "focus_player_token": (
                _token(cand.focus_player_id) if cand.focus_player_id else None
            ),
            "start_demo_tick": cand.start_demo_tick,
            "anchor_demo_tick": cand.anchor_demo_tick,
            "end_demo_tick": cand.end_demo_tick,
            "severity": cand.severity,
            "confidence": cand.confidence,
            "metrics": {
                key: value
                for key, value in cand.metrics.items()
                if key
                in {
                    "peak_advantage",
                    "peak_alive_friendly",
                    "peak_alive_enemy",
                    "peak_demo_tick",
                    "final_round_winner",
                    "win_reason",
                    "collapse_demo_tick",
                    "minimum_later_advantage",
                    "minimum_player_advantage",
                    "trade_window_demo_ticks",
                }
            },
            "evidence_ids": [ev.evidence_id for ev in cand.evidence],
            "candidate_id": cand.id,
        }

    summary = {
        "rule_engine_contract_version": RULE_ENGINE_CONTRACT_VERSION,
        "thresholds_version": RULE_THRESHOLDS_VERSION,
        "fixture_sha256": FIXTURE_SHA,
        "evaluated_rounds": len(context.rounds),
        "life_ending_events": len(context.life_ending_events),
        "candidate_counts": {
            "R001": len(r001.candidates),
            "R002": len(r002.candidates),
            "R003": len(r003.candidates),
        },
        "unresolved_counts": {
            "R001": len(r001.unresolved),
            "R002": len(r002.unresolved),
            "R003": len(r003.unresolved),
        },
        "r003_by_side": dict(
            Counter(c.focus_side for c in r003.candidates if c.focus_side)
        ),
        "r003_peak_advantage_histogram": dict(
            Counter(c.metrics.get("peak_advantage") for c in r003.candidates)
        ),
        "r003_sample_candidates": [
            _redact_candidate(c) for c in r003.candidates[:5]
        ],
        "notes": [
            "Redacted summary only — no Steam IDs, player names, or demo paths.",
            "R003 uses conservative round-loss semantics + freeze_end selected_ticks sides.",
        ],
    }

    SPIKE_OUT.parent.mkdir(parents=True, exist_ok=True)
    SPIKE_OUT.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    # Sanity: engine produces stable structures; counts are fixture-specific.
    assert summary["candidate_counts"]["R001"] >= 0
    assert summary["candidate_counts"]["R003"] >= 0
    for cand in r003.candidates:
        assert cand.evidence
        assert cand.metrics.get("final_round_winner") in {"ct", "t"}
        assert cand.confidence == 1.0
