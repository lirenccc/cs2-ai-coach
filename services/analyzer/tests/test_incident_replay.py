"""IncidentReplayPlan builder / API tests (CI-safe)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.incident_replay import (
    INCIDENT_REPLAY_PLAN_VERSION,
    REPLAY_SEMANTICS_VERSION,
    REPLAY_TICK_DOMAIN,
    build_incident_replay_plan,
    compute_seek_demo_tick,
    renderer_safe_plan,
)
from app.services.match_review import build_match_review_from_parsed
from app.storage.db import Database
from app.storage.match_repository import MatchRepository
from app.storage.migrations import migrate
from review_fixtures import synthetic_match_record, synthetic_review_parsed

TOKEN = "0123456789abcdef"


def _persist_synthetic(tmp_path: Path, *, dem_path: Path | None = None) -> str:
    db = Database(tmp_path / "replay.db")
    migrate(db)
    repo = MatchRepository(db)
    match = synthetic_match_record()
    source = dem_path or (tmp_path / "synthetic.dem")
    if dem_path is None:
        source.write_bytes(b"PBDEMS2\x00synthetic")
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO demos(id, sha256, original_path, size_bytes)
            VALUES (?, ?, ?, ?)
            """,
            (match.demo_id, "a" * 64, str(source), source.stat().st_size),
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


def test_compute_seek_uses_supplied_tick_rate_not_64():
    seek, source, rate, degraded = compute_seek_demo_tick(
        anchor_demo_tick=10_000,
        start_demo_tick=9_000,
        round_start_demo_tick=8_000,
        tick_rate=128.0,
        pre_roll_seconds=5.0,
    )
    assert seek == 10_000 - int(round(5.0 * 128.0))
    assert source == "match.tick_rate"
    assert rate == 128.0
    assert degraded is False


def test_compute_seek_clamps_to_round_start():
    seek, _, _, _ = compute_seek_demo_tick(
        anchor_demo_tick=950,
        start_demo_tick=900,
        round_start_demo_tick=900,
        tick_rate=64.0,
        pre_roll_seconds=5.0,
    )
    assert seek == 900


def test_null_timing_does_not_hardcode_64hz():
    seek, source, rate, degraded = compute_seek_demo_tick(
        anchor_demo_tick=5000,
        start_demo_tick=4800,
        round_start_demo_tick=4000,
        tick_rate=None,
        pre_roll_seconds=5.0,
    )
    assert seek == 4800
    assert source == "incident_start_demo_tick"
    assert rate is None
    assert degraded is True
    # Would be 5000 - 5*64 = 4680 if wrongly hard-coded.
    assert seek != 4680


def test_resolve_ticks_prefers_match_then_probe(tmp_path: Path):
    from app.services.incident_replay import resolve_ticks_per_second

    rate, source = resolve_ticks_per_second(128.0, None)
    assert rate == 128.0
    assert source == "match.tick_rate"

    rate2, source2 = resolve_ticks_per_second(None, str(tmp_path / "missing.dem"))
    assert rate2 is None
    assert source2 == "incident_start_demo_tick"


def test_build_plan_serialization_and_demotick_domain():
    match = synthetic_match_record()
    review = build_match_review_from_parsed(
        match=match, parsed=synthetic_review_parsed()
    )
    incident = next(i for i in review["incidents"] if i["rule_id"] == "R001")
    plan = build_incident_replay_plan(
        review=review,
        incident_id=incident["incident_id"],
        demo_sha256="b" * 64,
        demo_source_path=r"C:\private\match.dem",
    )
    assert plan["version"] == INCIDENT_REPLAY_PLAN_VERSION
    assert plan["replay_tick_domain"] == REPLAY_TICK_DOMAIN
    assert plan["replay_semantics_version"] == REPLAY_SEMANTICS_VERSION
    assert plan["demo_sha256"] == "b" * 64
    assert plan["demo_source_path"] == r"C:\private\match.dem"
    assert "server_tick" not in plan
    assert "seek_server_tick" not in plan
    assert plan["seek_demo_tick"] <= plan["anchor_demo_tick"]
    assert plan["pov_auto_selected"] is False

    safe = renderer_safe_plan(plan)
    assert "demo_source_path" not in safe
    assert "demo_sha256" in safe


def test_invalid_incident_id():
    match = synthetic_match_record()
    review = build_match_review_from_parsed(
        match=match, parsed=synthetic_review_parsed()
    )
    try:
        build_incident_replay_plan(
            review=review,
            incident_id="inc_does_not_exist",
            demo_sha256="c" * 64,
            demo_source_path=None,
        )
        raise AssertionError("expected INCIDENT_NOT_FOUND")
    except Exception as exc:  # noqa: BLE001
        assert getattr(exc, "code", None) == "INCIDENT_NOT_FOUND"


def test_api_replay_plan_and_privacy(tmp_path: Path):
    match_id = _persist_synthetic(tmp_path)
    settings = Settings(
        host="127.0.0.1",
        port=0,
        session_token=TOKEN,
        db_path=str(tmp_path / "replay.db"),
        extract_root=str(tmp_path / "extract"),
    )
    client = TestClient(create_app(settings))
    headers = {"x-cs2-coach-token": TOKEN}

    review = client.get(f"/v1/matches/{match_id}/review", headers=headers).json()
    incident = next(i for i in review["incidents"] if i["rule_id"] == "R002")

    response = client.get(
        f"/v1/matches/{match_id}/incidents/{incident['incident_id']}/replay-plan",
        headers=headers,
    )
    assert response.status_code == 200
    plan = response.json()
    assert plan["match_id"] == match_id
    assert plan["incident_id"] == incident["incident_id"]
    assert plan["replay_tick_domain"] == "DemoTick"
    assert plan["verified_tick_rate"] == 128.0
    assert plan["pre_roll_seconds"] == 5.0
    expected = incident["anchor_demo_tick"] - int(round(5.0 * 128.0))
    round_start = next(
        r["start_demo_tick"]
        for r in review["rounds"]
        if r["round_id"] == incident["round_id"]
    )
    assert plan["seek_demo_tick"] == max(round_start, expected)
    assert plan["demo_sha256"] == "a" * 64
    # Native may receive path; renderer contract tests exclude it separately.
    assert "session_token" not in plan
    assert "netcon_port" not in plan

    missing = client.get(
        f"/v1/matches/{match_id}/incidents/inc_missing/replay-plan",
        headers=headers,
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "INCIDENT_NOT_FOUND"
