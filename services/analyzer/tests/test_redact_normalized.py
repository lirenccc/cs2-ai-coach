from __future__ import annotations

import json
from pathlib import Path

from app.demo.models import (
    NORMALIZATION_SCHEMA_VERSION,
    DamageRow,
    GrenadeRow,
    KillRow,
    MatchHeader,
    ParsedDemo,
    PlayerRosterEntry,
    RoundRow,
    SelectedTickRow,
)
from app.demo.redact import redact_parsed_demo


def test_redact_strips_names_and_steamids() -> None:
    parsed = ParsedDemo(
        parser_name="demoparser2",
        parser_version="0.42.0",
        normalization_schema_version=NORMALIZATION_SCHEMA_VERSION,
        header=MatchHeader(
            map_name="de_dust2",
            patch_version="14189",
            build_num="10924",
            tick_rate=64.0,
            playback_ticks=115418,
            playback_time_seconds=1803.40625,
            server_start_tick=3779,
            extras={"timing_source": "structural_probe_file_info"},
        ),
        roster=[
            PlayerRosterEntry(
                player_id="steam:1",
                steamid64="76561198000000001",
                display_name="SecretName",
                team="CT",
                userid=3,
            ),
            PlayerRosterEntry(
                player_id="hltv:cstv",
                steamid64=None,
                display_name="CSTV",
                is_hltv=True,
                userid=0,
            ),
        ],
        rounds=[RoundRow(round_number=1, freeze_end_tick=100, end_tick=180)],
        kills=[
            KillRow(
                event_id="kill:1",
                tick=120,
                attacker_id="steam:2",
                victim_id="steam:1",
                demo_tick=120,
                server_tick=3900,
                victim_userid=3,
                victim_pawn=-123,
            )
        ],
        damages=[
            DamageRow(
                event_id="damage:1",
                tick=110,
                attacker_id="steam:2",
                victim_id="steam:1",
                hp_damage=10,
                demo_tick=110,
                server_tick=3890,
            )
        ],
        grenades=[
            GrenadeRow(
                event_id="grenade:1",
                tick=130,
                grenade_type="flashbang",
                thrower_id="steam:2",
            )
        ],
        selected_ticks=[
            SelectedTickRow(
                demo_tick=100,
                player_id="steam:1",
                steamid64="76561198000000001",
                x=1.0,
                y=2.0,
                z=3.0,
                health=100.0,
                team="CT",
                is_alive=True,
                selection_reason="round_freeze_end",
            )
        ],
        event_counts={
            "player_death": 1,
            "player_hurt": 1,
            "weapon_fire": 10,
            "round_freeze_end": 1,
            "flashbang_detonate": 1,
            "hegrenade_detonate": 0,
            "smokegrenade_detonate": 0,
            "inferno_startburn": 0,
            "decoy_detonate": 0,
        },
    )

    redacted = redact_parsed_demo(parsed.to_dict())
    blob = json.dumps(redacted)
    assert "SecretName" not in blob
    assert "76561198000000001" not in blob
    assert "display_name" not in blob
    assert redacted["roster"]["human_count"] == 1
    assert redacted["roster"]["hltv_count"] == 1
    assert redacted["kills"]["with_victim_userid"] == 1


def test_committed_redacted_normalized_golden_exists() -> None:
    path = (
        Path(__file__).resolve().parents[3]
        / "fixtures"
        / "real-demo"
        / "expected"
        / "9208210907649202700_0.redacted-normalized.json"
    )
    assert path.exists()
    summary = json.loads(path.read_text(encoding="utf-8"))
    assert summary["header"]["map_name"] == "de_dust2"
    assert summary["header"]["patch_version"] == "14189"
    assert summary["header"]["build_num"] == "10924"
    assert summary["header"]["tick_rate"] == 64.0
    assert summary["events"]["player_death"] == 128
    assert summary["events"]["player_hurt"] == 444
    assert summary["events"]["weapon_fire"] == 2894
    assert summary["events"]["round_freeze_end"] == 18
    assert summary["roster"]["human_count"] >= 10
    assert summary["roster"]["hltv_count"] == 1
    assert "display_name" not in json.dumps(summary)
