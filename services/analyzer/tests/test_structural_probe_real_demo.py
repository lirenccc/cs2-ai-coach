from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.demo.archive import resolve_demo_file
from app.demo.structural_probe import probe_demo


@pytest.mark.skipif(
    not os.environ.get("CS2_COACH_REAL_DEMO"),
    reason="set CS2_COACH_REAL_DEMO to a .dem or .zip path for private regression",
)
def test_real_demo_regression(tmp_path: Path):
    source = Path(os.environ["CS2_COACH_REAL_DEMO"])
    resolved = resolve_demo_file(source, extract_root=tmp_path / "extracted")
    summary, _ = probe_demo(resolved.demo_path)

    assert summary.sha256 == "d873502ed8a1df0cd0f919568261e14b92a04e1ca44cd60e84dcec64748a01ec"
    assert summary.header["map_name"] == "de_dust2"
    assert summary.header["patch_version"] == 14189
    assert summary.header["build_num"] == 10924
    assert summary.playback["playback_ticks"] == 115418
    assert summary.playback["playback_time_seconds"] == 1803.40625
    assert summary.playback["derived_tick_rate"] == 64.0
    assert summary.outer_frame_count == 115484
    assert summary.event_schema_count == 271
    assert summary.legacy_event_count == 17432
    assert summary.unique_legacy_event_types == 47
    assert summary.event_counts["round_freeze_end"] == 18
    assert summary.event_counts["player_death"] == 128
    assert summary.event_counts["player_hurt"] == 444
    assert summary.event_counts["weapon_fire"] == 2894
    assert len([p for p in summary.roster if p.steamid64 != 0]) == 10
