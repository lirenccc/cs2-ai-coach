"""P0.6A contract tests — redacted fixtures only (no private Demo required)."""

from __future__ import annotations

import json
from pathlib import Path

from app.domain.evidence import (
    EVIDENCE_LINEAGE_VERSION,
    IDENTITY_SEMANTICS_VERSION,
    ROUND_SIDE_CONTRACT_VERSION,
    EvidenceLineage,
    RoundPlayerState,
    assert_lineage_versions,
    side_from_team_num,
)
from app.domain.takeover import build_a03_takeover_timeline


FIXTURES = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "spikes"
    / "capture"
    / "fixtures"
)


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_evidence_lineage_version_and_optional_fields() -> None:
    lineage = EvidenceLineage(
        evidence_lineage_version=EVIDENCE_LINEAGE_VERSION,
        match_id="9208210907649202700_0",
        frame_id="frame-0001",
        frame_sha256="abc",
        requested_demo_tick=4354,
        replay_calibration_version="p0.5a-2026-10-10",
        cs2_build_identity="patch=1.41.9.0;client=2000930;buildid=25815307",
        parser_event_id=None,
        player_identity_id=None,
    )
    assert_lineage_versions(lineage)
    payload = lineage.to_dict()
    assert payload["player_identity_id"] is None
    assert payload["requested_demo_tick"] == 4354
    assert "display_name" not in payload


def test_pawn_lifecycle_fixture_invariants() -> None:
    data = _load("pawn_lifecycle.redacted.json")
    assert data["identity_semantics_version"] == IDENTITY_SEMANTICS_VERSION
    assert data["verified"]["pawn_handle_alone_is_not_match_unique"] is True
    assert data["verified"]["do_not_use_round_player_as_unique_life_key"] is True
    lives = data["ordinary_multi_life"]["lives"]
    handles = {life["pawn_handle"] for life in lives}
    assert len(handles) >= 2
    assert data["pawn_handle_reuse"]["pawn_handle"] == 432572463
    assert set(data["pawn_handle_reuse"]["observed_on_controllers"]) == {"C3", "C4", "C8"}


def test_bot_takeover_timeline_matches_builder() -> None:
    fixture = _load("bot_takeover_timeline.redacted.json")
    built = build_a03_takeover_timeline().to_dict()
    assert fixture["takeover"]["demo_tick"] == built["demo_tick"] == 33717
    assert fixture["before"]["pawn_handle"] == built["before"]["pawn_handle"]
    assert fixture["after"]["pawn_handle"] == built["after"]["pawn_handle"]
    assert fixture["before"]["pawn_handle"] != fixture["after"]["pawn_handle"]
    assert fixture["botid_equals_userid"] is True
    trade = next(a for a in fixture["attribution"] if a["kind"] == "trade_opportunity")
    assert trade["certainty"] == "unresolved"
    death = next(a for a in fixture["attribution"] if a["kind"] == "death")
    assert death["certainty"] == "verified"


def test_round_side_switches_across_halftime() -> None:
    data = _load("round_side_states.redacted.json")
    assert data["round_side_contract_version"] == ROUND_SIDE_CONTRACT_VERSION
    by_round = {s["round_id"]: s for s in data["samples"]}
    r1 = {p["player_identity_id"]: p["side"] for p in by_round[1]["players"]}
    r12 = {p["player_identity_id"]: p["side"] for p in by_round[12]["players"]}
    r13 = {p["player_identity_id"]: p["side"] for p in by_round[13]["players"]}
    r18 = {p["player_identity_id"]: p["side"] for p in by_round[18]["players"]}
    assert r1 == r12
    assert r13 == r18
    assert all(r1[i] != r13[i] for i in r1)
    # Contract object for rule consumers
    sample = by_round[13]["players"][0]
    state = RoundPlayerState(
        round_id=13,
        player_identity_id=sample["player_identity_id"],
        side=sample["side"],
        team_identity=None,
        source=sample["source"],
    )
    assert state.side in {"t", "ct"}
    assert side_from_team_num(sample["team_num"]) == sample["side"]


def test_capture_at_event_fixture_uses_demo_tick_calibration() -> None:
    data = _load("capture_at_event.redacted.json")
    assert data["evidence_lineage_version"] == EVIDENCE_LINEAGE_VERSION
    assert data["replay_calibration_version"] == "p0.5a-2026-10-10"
    ticks = {a["requested_demo_tick"] for a in data["anchors"]}
    assert 0 not in ticks
    assert ticks == {4354, 42294, 79639}
    for anchor in data["anchors"]:
        assert anchor["seek_calibration_version"] == "p0.5a-2026-10-10"
        assert anchor["semantic_result"] in {
            "correct_event_window",
            "early",
            "late",
            "wrong_round",
            "not_visually_observable",
        }
