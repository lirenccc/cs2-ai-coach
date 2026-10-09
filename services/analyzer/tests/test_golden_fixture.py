from __future__ import annotations

import json
from pathlib import Path


def test_redacted_real_demo_summary_is_present() -> None:
    path = (
        Path(__file__).resolve().parents[3]
        / "fixtures"
        / "real-demo"
        / "expected"
        / "9208210907649202700_0.redacted-summary.json"
    )
    summary = json.loads(path.read_text(encoding="utf-8"))

    assert summary["header"]["map_name"] == "de_dust2"
    assert summary["header"]["patch_version"] == 14189
    assert summary["header"]["build_num"] == 10924
    assert summary["playback"]["verified_tick_rate"] == 64.0
    assert summary["events"]["round_freeze_end"] == 18
    assert summary["events"]["player_death"] == 128
    assert summary["events"]["player_hurt"] == 444
    assert summary["events"]["weapon_fire"] == 2894
    assert summary["roster"]["human_count"] == 10
    assert "display_name" not in json.dumps(summary)
