"""Opt-in private P0.2 demo smoke for Match Review serialization.

Requires CS2_COACH_REAL_DEMO. Does not require CS2, NetCon, capture, or OpenAI.
Does not commit private review payloads.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.demo.archive import resolve_demo_file
from app.demo.factory import create_demo_parser
from app.services.match_review import build_match_review_from_parsed
from app.storage.match_repository import MatchRecord

FIXTURE_SHA = "d873502ed8a1df0cd0f919568261e14b92a04e1ca44cd60e84dcec64748a01ec"
SPIKE_OUT = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "spikes"
    / "review"
    / "fixtures"
    / "p0_2_match_review_summary.redacted.json"
)


@pytest.mark.skipif(
    not os.environ.get("CS2_COACH_REAL_DEMO"),
    reason="set CS2_COACH_REAL_DEMO to a .dem or .zip path for private review smoke",
)
def test_private_demo_match_review_smoke(tmp_path: Path):
    source = Path(os.environ["CS2_COACH_REAL_DEMO"])
    resolved = resolve_demo_file(source, extract_root=tmp_path / "extracted")
    parsed = create_demo_parser().parse(resolved.demo_path)

    match = MatchRecord(
        id=f"demo:{FIXTURE_SHA[:16]}",
        demo_id=f"demo:{FIXTURE_SHA[:16]}",
        map_name=parsed.header.map_name,
        parser_name=parsed.parser_name,
        parser_version=parsed.parser_version,
        normalization_schema_version=parsed.normalization_schema_version,
        parse_status="completed",
        roster_count=len(parsed.roster),
        round_count=len(parsed.rounds),
        kill_count=len(parsed.kills),
        damage_count=len(parsed.damages),
    )
    # Never feed absolute private paths into the review builder.
    parsed_no_path = parsed.__class__(
        parser_name=parsed.parser_name,
        parser_version=parsed.parser_version,
        normalization_schema_version=parsed.normalization_schema_version,
        header=parsed.header,
        roster=parsed.roster,
        rounds=parsed.rounds,
        kills=parsed.kills,
        damages=parsed.damages,
        grenades=parsed.grenades,
        selected_ticks=parsed.selected_ticks,
        event_counts=parsed.event_counts,
        source_path=None,
    )
    review = build_match_review_from_parsed(match=match, parsed=parsed_no_path)

    assert review["rounds"]
    # tick_rate may be absent from some parser paths; UI must tolerate null.
    assert "tick_rate" in review["match"]
    dumped = json.dumps(review)
    assert "CS2_COACH_REAL_DEMO" not in dumped
    assert str(source) not in dumped

    # Every emitted candidate must serialize into the review contract.
    by_rule = {row["rule_id"]: row["matched"] for row in review["analysis_coverage"]}
    assert by_rule.get("R001", 0) == sum(
        1 for i in review["incidents"] if i["rule_id"] == "R001"
    )
    assert by_rule.get("R002", 0) == sum(
        1 for i in review["incidents"] if i["rule_id"] == "R002"
    )
    assert by_rule.get("R003", 0) == sum(
        1 for i in review["incidents"] if i["rule_id"] == "R003"
    )
    for incident in review["incidents"]:
        assert incident["incident_id"]
        assert incident["anchor_demo_tick"] >= 0
        assert "evidence" in incident
        assert incident["incident_type"] != "throw"

    # Unresolved never masquerades as incidents.
    assert all(i["status"] == "candidate" for i in review["incidents"])

    summary = {
        "schema_version": review["schema_version"],
        "rule_engine_contract_version": review["rule_engine_contract_version"],
        "thresholds_version": review["thresholds_version"],
        "fixture_sha256": FIXTURE_SHA,
        "round_count": len(review["rounds"]),
        "timeline_event_count": len(review["timeline_events"]),
        "incident_counts": {
            "R001": by_rule.get("R001", 0),
            "R002": by_rule.get("R002", 0),
            "R003": by_rule.get("R003", 0),
        },
        "unresolved_counts": {
            row["rule_id"]: row["unresolved"] for row in review["analysis_coverage"]
        },
        "notes": [
            "Redacted summary only — no Steam IDs, player names, or demo paths.",
            "Private review payload is not committed.",
        ],
    }
    SPIKE_OUT.parent.mkdir(parents=True, exist_ok=True)
    SPIKE_OUT.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
