from __future__ import annotations

from app.demo.normalize import (
    assign_round_number,
    build_rounds_from_markers,
    stable_player_id,
)


def test_stable_player_id_prefers_steamid() -> None:
    assert stable_player_id(steamid="76561198000000001", name="Nick") == (
        "steam:76561198000000001"
    )
    assert stable_player_id(steamid=0, name="Nick").startswith("name:")


def test_round_state_machine_uses_win_panel_fallback() -> None:
    rounds = build_rounds_from_markers(
        freeze_end_ticks=[100, 200],
        officially_ended_ticks=[180],
        win_panel_ticks=[260],
    )
    assert rounds == [
        (1, 100, 180),
        (2, 200, 260),
    ]
    assert assign_round_number(120, rounds) == 1
    assert assign_round_number(220, rounds) == 2
