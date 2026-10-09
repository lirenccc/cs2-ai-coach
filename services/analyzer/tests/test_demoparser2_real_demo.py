from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.demo.archive import resolve_demo_file
from app.demo.demoparser2_adapter import Demoparser2Adapter
from app.demo.redact import redact_parsed_demo
from app.demo.structural_probe import probe_demo


GOLDEN_NORMALIZED = (
    Path(__file__).resolve().parents[3]
    / "fixtures"
    / "real-demo"
    / "expected"
    / "9208210907649202700_0.redacted-normalized.json"
)


@pytest.mark.skipif(
    not os.environ.get("CS2_COACH_REAL_DEMO"),
    reason="set CS2_COACH_REAL_DEMO to a .dem or .zip path for demoparser2 cross-check",
)
def test_demoparser2_full_parser_matches_structural_probe(tmp_path: Path) -> None:
    source = Path(os.environ["CS2_COACH_REAL_DEMO"])
    adapter = Demoparser2Adapter()
    if not adapter.available():
        pytest.skip("demoparser2 is not installed")

    resolved = resolve_demo_file(source, extract_root=tmp_path / "extracted")

    # 1) Structural probe first — summary retained in test output / assertions.
    probe_summary, _ = probe_demo(resolved.demo_path)
    probe_dict = {
        "sha256": probe_summary.sha256,
        "map_name": probe_summary.header["map_name"],
        "patch_version": probe_summary.header["patch_version"],
        "build_num": probe_summary.header["build_num"],
        "derived_tick_rate": probe_summary.playback["derived_tick_rate"],
        "event_counts": {
            key: probe_summary.event_counts[key]
            for key in (
                "round_freeze_end",
                "player_death",
                "player_hurt",
                "weapon_fire",
                "flashbang_detonate",
                "hegrenade_detonate",
                "smokegrenade_detonate",
            )
        },
        "human_roster": len([p for p in probe_summary.roster if p.steamid64 != 0]),
        "hltv_roster": len([p for p in probe_summary.roster if p.is_hltv]),
    }
    print("structural_probe_summary=", json.dumps(probe_dict, ensure_ascii=True))

    # 2) Full demoparser2 normalize against the same file.
    parsed = adapter.parse(resolved.demo_path)

    assert parsed.parser_name == "demoparser2"
    assert parsed.parser_version is not None
    assert parsed.normalization_schema_version == "2"
    assert parsed.header.map_name == "de_dust2"
    assert parsed.header.patch_version == "14189"
    assert parsed.header.build_num == "10924"
    assert parsed.header.tick_rate == 64.0
    assert parsed.header.playback_ticks == 115418
    assert parsed.header.server_start_tick == 3779

    assert parsed.event_counts["player_death"] == probe_summary.event_counts["player_death"] == 128
    assert parsed.event_counts["player_hurt"] == probe_summary.event_counts["player_hurt"] == 444
    assert (
        parsed.event_counts["round_freeze_end"]
        == probe_summary.event_counts["round_freeze_end"]
        == 18
    )
    assert parsed.event_counts["weapon_fire"] == probe_summary.event_counts["weapon_fire"] == 2894
    assert (
        parsed.event_counts["flashbang_detonate"]
        == probe_summary.event_counts["flashbang_detonate"]
        == 64
    )
    assert (
        parsed.event_counts["hegrenade_detonate"]
        == probe_summary.event_counts["hegrenade_detonate"]
        == 18
    )
    assert (
        parsed.event_counts["smokegrenade_detonate"]
        == probe_summary.event_counts["smokegrenade_detonate"]
        == 56
    )

    assert len(parsed.rounds) == 18
    assert len(parsed.kills) == 128
    assert len(parsed.damages) == 444
    assert len(parsed.grenades) >= 64 + 18 + 56

    humans = [
        row
        for row in parsed.roster
        if not row.is_hltv
        and not row.is_bot
        and row.steamid64
        and row.steamid64.startswith("7656")
    ]
    hltv = [row for row in parsed.roster if row.is_hltv]
    assert len(humans) == 10
    assert len(hltv) == 1
    assert all(row.team in {"T", "CT"} for row in humans)
    # Team codes come from entity team_number, not kill relationships.
    assert {row.team for row in humans} == {"T", "CT"}

    assert all(kill.demo_tick is not None for kill in parsed.kills)
    assert all(kill.server_tick is not None for kill in parsed.kills)
    assert all(kill.victim_userid is not None for kill in parsed.kills)
    assert all(kill.victim_pawn is not None for kill in parsed.kills)
    # Identity is event_id; player+round must not be treated as unique.
    assert len({kill.event_id for kill in parsed.kills}) == len(parsed.kills)

    assert parsed.selected_ticks
    assert {row.selection_reason for row in parsed.selected_ticks} == {"round_freeze_end"}
    assert len({row.demo_tick for row in parsed.selected_ticks}) == 18

    redacted = redact_parsed_demo(parsed.to_dict())
    assert "display_name" not in json.dumps(redacted)
    assert "steamid64" not in json.dumps(redacted)
    print("redacted_normalized=", json.dumps(redacted, ensure_ascii=True))

    if GOLDEN_NORMALIZED.exists():
        golden = json.loads(GOLDEN_NORMALIZED.read_text(encoding="utf-8"))
        assert redacted["header"] == golden["header"]
        assert redacted["events"] == golden["events"]
        assert redacted["roster"]["human_count"] == golden["roster"]["human_count"]
        assert redacted["roster"]["hltv_count"] == golden["roster"]["hltv_count"]
        assert redacted["kills"]["count"] == golden["kills"]["count"]
        assert redacted["selected_ticks"]["unique_demo_ticks"] == golden[
            "selected_ticks"
        ]["unique_demo_ticks"]
