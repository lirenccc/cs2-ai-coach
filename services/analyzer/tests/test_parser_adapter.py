from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.demo.awpy_adapter import AwpyAdapter
from app.demo.composite import CompositeDemoParser
from app.demo.demoparser2_adapter import Demoparser2Adapter
from app.demo.frames import frame_to_records
from app.demo.models import (
    NORMALIZATION_SCHEMA_VERSION,
    DamageRow,
    KillRow,
    MatchHeader,
    ParsedDemo,
    PlayerRosterEntry,
    RoundRow,
)
from app.errors import MissingExpectedEventError, ParserUnavailableError


FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "minimal_demoparser_frames.json"
)


class _Frame:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows

    def to_dict(self, orient: str = "records"):
        if orient != "records":
            raise TypeError(orient)
        return list(self._rows)


class _FakeDemoParser:
    def __init__(self, payload: dict[str, Any]):
        self.payload = payload

    def parse_header(self):
        return dict(self.payload["header"])

    def parse_player_info(self):
        return _Frame(self.payload["players"])

    def parse_event(self, event_name: str, **_kwargs):
        return _Frame(list(self.payload.get(event_name, [])))

    def parse_ticks(self, fields: list[str], ticks: list[int] | None = None):
        selected = ticks or [1]
        return _Frame(
            [
                {
                    "tick": tick,
                    "steamid": "76561198000000001",
                    "name": "Alpha",
                    "X": 1.0,
                    "Y": 2.0,
                    "Z": 3.0,
                    "health": 100,
                    "team_num": 3,
                    "is_alive": True,
                    "field": fields[0] if fields else None,
                }
                for tick in selected
            ]
        )


def test_frame_to_records_accepts_dict_list_and_dataframe_like() -> None:
    assert frame_to_records([{"a": 1}]) == [{"a": 1}]
    assert frame_to_records(_Frame([{"a": 2}])) == [{"a": 2}]
    with pytest.raises(TypeError):
        frame_to_records(object())


def test_demoparser2_adapter_normalizes_fixture_without_network(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    demo_path = tmp_path / "fixture.dem"
    demo_path.write_bytes(b"x" * 2048)

    monkeypatch.setattr(
        "app.demo.demoparser2_adapter.Demoparser2Adapter.available",
        lambda self: True,
    )
    monkeypatch.setattr(
        "app.demo.demoparser2_adapter.Demoparser2Adapter.version",
        lambda self: "0.42.0-fixture",
    )
    monkeypatch.setattr(
        "app.demo.demoparser2_adapter.Demoparser2Adapter._parser",
        lambda self, path: _FakeDemoParser(payload),
    )

    parsed = Demoparser2Adapter().parse(demo_path)

    assert isinstance(parsed, ParsedDemo)
    assert parsed.parser_name == "demoparser2"
    assert parsed.parser_version == "0.42.0-fixture"
    assert parsed.normalization_schema_version == NORMALIZATION_SCHEMA_VERSION
    assert parsed.header.map_name == "de_dust2"
    assert len(parsed.roster) == 2
    assert len(parsed.rounds) == 2
    assert parsed.rounds[0].end_tick == 180
    assert parsed.rounds[1].end_tick == 260
    assert len(parsed.kills) == 2
    assert len(parsed.damages) == 2
    assert parsed.kills[0].victim_id == "steam:76561198000000001"
    assert parsed.kills[0].round_number == 1
    assert parsed.kills[0].demo_tick == 120
    assert parsed.damages[1].hp_damage == 54
    assert parsed.event_counts["player_death"] == 2
    assert parsed.event_counts["weapon_fire"] == 1
    assert len(parsed.grenades) == 1
    assert parsed.grenades[0].grenade_type == "flashbang"
    assert len(parsed.selected_ticks) == 2
    assert parsed.roster[0].team == "CT"
    assert parsed.roster[1].team == "T"
    # No DataFrame leaked into the domain result.
    assert all(isinstance(row, KillRow) for row in parsed.kills)
    assert all(isinstance(row, DamageRow) for row in parsed.damages)
    assert all(isinstance(row, RoundRow) for row in parsed.rounds)
    assert all(isinstance(row, PlayerRosterEntry) for row in parsed.roster)
    assert isinstance(parsed.header, MatchHeader)
    assert "DataFrame" not in repr(parsed.to_dict())


def test_demoparser2_rejects_empty_event_tables_on_large_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    demo_path = tmp_path / "emptyish.dem"
    demo_path.write_bytes(b"x" * 2048)
    empty = {
        "header": {"map_name": "de_dust2"},
        "players": [],
        "player_death": [],
        "player_hurt": [],
        "round_freeze_end": [],
        "round_officially_ended": [],
        "cs_win_panel_match": [],
    }
    monkeypatch.setattr(
        "app.demo.demoparser2_adapter.Demoparser2Adapter.available",
        lambda self: True,
    )
    monkeypatch.setattr(
        "app.demo.demoparser2_adapter.Demoparser2Adapter._parser",
        lambda self, path: _FakeDemoParser(empty),
    )
    with pytest.raises(MissingExpectedEventError):
        Demoparser2Adapter().parse(demo_path)


def test_awpy_unavailable_without_install() -> None:
    adapter = AwpyAdapter()
    if adapter.available():
        pytest.skip("awpy is installed in this environment")
    assert adapter.version() is None
    with pytest.raises(ParserUnavailableError):
        adapter.parse(Path("missing.dem"))


def test_composite_fills_gaps_from_fallback() -> None:
    incomplete = ParsedDemo(
        parser_name="awpy",
        parser_version="1.0",
        normalization_schema_version=NORMALIZATION_SCHEMA_VERSION,
        header=MatchHeader(map_name=None),
        roster=[],
        rounds=[],
        kills=[],
        damages=[],
    )
    complete = ParsedDemo(
        parser_name="demoparser2",
        parser_version="0.42.0",
        normalization_schema_version=NORMALIZATION_SCHEMA_VERSION,
        header=MatchHeader(map_name="de_inferno"),
        roster=[
            PlayerRosterEntry(
                player_id="steam:1",
                steamid64="1",
                display_name="A",
            )
        ],
        rounds=[RoundRow(round_number=1, freeze_end_tick=10, end_tick=20)],
        kills=[
            KillRow(
                event_id="kill:1",
                tick=12,
                attacker_id="steam:2",
                victim_id="steam:1",
            )
        ],
        damages=[
            DamageRow(
                event_id="damage:1",
                tick=11,
                attacker_id="steam:2",
                victim_id="steam:1",
                hp_damage=10,
            )
        ],
    )

    class _Primary:
        name = "awpy"

        def available(self) -> bool:
            return True

        def version(self) -> str | None:
            return "1.0"

        def parse(self, demo_path: Path) -> ParsedDemo:
            return incomplete

    class _Fallback:
        name = "demoparser2"

        def available(self) -> bool:
            return True

        def version(self) -> str | None:
            return "0.42.0"

        def parse(self, demo_path: Path) -> ParsedDemo:
            return complete

    merged = CompositeDemoParser(_Primary(), _Fallback()).parse(Path("x.dem"))
    assert merged.parser_name == "awpy+demoparser2"
    assert merged.header.map_name == "de_inferno"
    assert len(merged.kills) == 1
    assert len(merged.roster) == 1
