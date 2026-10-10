"""Match Review API / builder tests (CI-safe synthetic fixture)."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.demo.hydrate import parsed_demo_from_dict
from app.main import create_app
from app.services.match_review import (
    MATCH_REVIEW_SCHEMA_VERSION,
    MatchReviewService,
    build_match_review_from_parsed,
    sort_incidents,
)
from app.storage.db import Database
from app.storage.match_repository import MatchRepository
from app.storage.migrations import migrate
from review_fixtures import synthetic_match_record, synthetic_review_parsed

TOKEN = "0123456789abcdef"


def _persist_synthetic(tmp_path: Path) -> str:
    db = Database(tmp_path / "review.db")
    migrate(db)
    repo = MatchRepository(db)
    match = synthetic_match_record()
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO demos(id, sha256, original_path, size_bytes)
            VALUES (?, ?, ?, ?)
            """,
            (match.demo_id, "a" * 64, "synthetic.dem", 1),
        )
        conn.execute(
            """
            INSERT INTO matches(
                id, demo_id, map_name, parser_name, parser_version,
                normalization_schema_version, parse_status,
                roster_count, round_count, kill_count, damage_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                match.id,
                match.demo_id,
                match.map_name,
                match.parser_name,
                match.parser_version,
                match.normalization_schema_version,
                match.parse_status,
                match.roster_count,
                match.round_count,
                match.kill_count,
                match.damage_count,
            ),
        )
        conn.commit()
    repo.save_parsed(match.id, synthetic_review_parsed())
    return match.id


def test_hydrate_roundtrip_strips_usable():
    parsed = synthetic_review_parsed()
    again = parsed_demo_from_dict(parsed.to_dict())
    assert again.header.tick_rate == 128.0
    assert len(again.kills) == len(parsed.kills)
    assert again.rounds[0].round_number == 1


def test_build_review_core_invariants():
    match = synthetic_match_record()
    parsed = synthetic_review_parsed()
    review = build_match_review_from_parsed(match=match, parsed=parsed)

    assert review["schema_version"] == MATCH_REVIEW_SCHEMA_VERSION
    assert "source_path" not in review["match"]
    assert "original_path" not in review["match"]
    assert review["match"]["tick_rate"] == 128.0

    round_numbers = [r["round_number"] for r in review["rounds"]]
    assert round_numbers == sorted(round_numbers)
    assert 2 in round_numbers  # zero-incident-ish round still listed

    rule_ids = {c["rule_id"] for c in review["incidents"]}
    assert "R001" in rule_ids
    assert "R002" in rule_ids
    assert "R003" in rule_ids

    # UNRESOLVED must not appear in incidents.
    assert all(i["status"] == "candidate" for i in review["incidents"])
    assert review["unresolved_evaluations"]
    assert any(
        u["reason_code"] == "TAKEOVER_ATTRIBUTION_UNRESOLVED"
        for u in review["unresolved_evaluations"]
    )

    # R003 label remains candidate / non-blaming.
    r003 = [i for i in review["incidents"] if i["rule_id"] == "R003"]
    assert r003
    assert all(i["incident_type"] == "ADVANTAGE_LOSS_CANDIDATE" for i in r003)
    assert all(i["thresholds_version"] for i in r003)
    assert all("peak_advantage" in i["metrics"] for i in r003)

    # Same-tick deaths share demo_tick; ordering by event_id is stable.
    same_tick = [
        e
        for e in review["timeline_events"]
        if e["event_type"] == "player_death" and e["demo_tick"] == 200
    ]
    assert len(same_tick) == 2
    assert [e["event_id"] for e in same_tick] == sorted(e["event_id"] for e in same_tick)

    # Post-halftime side for opening victim is T (not initial roster CT).
    r13 = [
        i
        for i in review["incidents"]
        if i["rule_id"] == "R001" and i["round_number"] == 13
    ]
    assert r13
    assert r13[0]["focus_side"] == "t"

    # Bomb outcome surfaced without inventing plant events.
    assert any(e["event_type"] == "bomb_defused" for e in review["timeline_events"])
    assert any(e["event_type"] == "bomb_exploded" for e in review["timeline_events"])

    # Coverage separates matched vs unresolved.
    by_rule = {row["rule_id"]: row for row in review["analysis_coverage"]}
    assert by_rule["R001"]["matched"] >= 1
    assert by_rule["R001"]["unresolved"] >= 1 or by_rule["R002"]["unresolved"] >= 1


def test_incident_ordering_stable_under_shuffle():
    match = synthetic_match_record()
    review = build_match_review_from_parsed(
        match=match, parsed=synthetic_review_parsed()
    )
    incidents = list(review["incidents"])
    shuffled = list(reversed(incidents))
    assert sort_incidents(shuffled) == sort_incidents(incidents)
    assert review["incidents"] == sort_incidents(incidents)


def test_review_api_and_privacy(tmp_path: Path):
    match_id = _persist_synthetic(tmp_path)
    settings = Settings(
        analyzer_host="127.0.0.1",
        analyzer_port=8765,
        session_token=TOKEN,
        db_path=tmp_path / "review.db",
        extract_root=tmp_path / "extracted",
    )
    with TestClient(create_app(settings)) as client:
        assert client.get(f"/v1/matches/{match_id}/review").status_code == 401
        missing = client.get(
            "/v1/matches/does-not-exist/review",
            headers={"x-cs2-coach-token": TOKEN},
        )
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "MATCH_NOT_FOUND"

        response = client.get(
            f"/v1/matches/{match_id}/review",
            headers={"x-cs2-coach-token": TOKEN},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        dumped = json.dumps(body)
        assert "should-not-leak" not in dumped
        assert "C:/" not in dumped
        assert "session_token" not in dumped
        assert body["match"]["match_id"] == match_id
        assert body["incidents"]
        assert "unresolved_evaluations" in body

        # Service path matches HTTP serialization.
        service_body = MatchReviewService(MatchRepository(Database(tmp_path / "review.db"))).get_review(
            match_id
        )
        assert service_body["match"]["match_id"] == body["match"]["match_id"]
        assert len(service_body["incidents"]) == len(body["incidents"])
