from __future__ import annotations

from pathlib import Path

from app.demo.models import (
    NORMALIZATION_SCHEMA_VERSION,
    DamageRow,
    KillRow,
    MatchHeader,
    ParsedDemo,
    PlayerRosterEntry,
    RoundRow,
)
from app.services.import_demo import ImportDemoService
from app.storage.db import Database
from app.storage.demo_repository import DemoRepository
from app.storage.match_repository import MatchRepository
from app.storage.migrations import migrate


class _FakeParser:
    name = "fake"

    def available(self) -> bool:
        return True

    def version(self) -> str | None:
        return "9.9.9"

    def parse(self, demo_path: Path) -> ParsedDemo:
        return ParsedDemo(
            parser_name=self.name,
            parser_version=self.version(),
            normalization_schema_version=NORMALIZATION_SCHEMA_VERSION,
            header=MatchHeader(map_name="de_dust2", patch_version="14189"),
            roster=[
                PlayerRosterEntry(
                    player_id="steam:1",
                    steamid64="1",
                    display_name="A",
                    team="ct",
                )
            ],
            rounds=[RoundRow(round_number=1, freeze_end_tick=10, end_tick=20)],
            kills=[
                KillRow(
                    event_id="kill:1",
                    tick=12,
                    attacker_id="steam:2",
                    victim_id="steam:1",
                    weapon="ak47",
                )
            ],
            damages=[
                DamageRow(
                    event_id="damage:1",
                    tick=11,
                    attacker_id="steam:2",
                    victim_id="steam:1",
                    hp_damage=27,
                )
            ],
            source_path=str(demo_path),
        )


def test_import_persists_parsed_demo_into_matches(tmp_path: Path) -> None:
    db = Database(tmp_path / "app.db")
    migrate(db)
    dem = tmp_path / "match.dem"
    dem.write_bytes(b"PBDEMS2\x00not-a-real-demo-but-hashed")

    service = ImportDemoService(
        DemoRepository(db),
        MatchRepository(db),
        _FakeParser(),
        extract_root=tmp_path / "extracted",
    )
    result = service.execute(str(dem))

    assert result.deduplicated is False
    assert result.match.parse_status == "completed"
    assert result.match.map_name == "de_dust2"
    assert result.match.parser_name == "fake"
    assert result.match.parser_version == "9.9.9"
    assert result.match.kill_count == 1
    assert result.match.damage_count == 1
    assert result.match.round_count == 1
    assert result.match.roster_count == 1

    payload = MatchRepository(db).load_parsed_json(result.match.id)
    assert payload is not None
    assert payload["header"]["map_name"] == "de_dust2"
    assert payload["kills"][0]["weapon"] == "ak47"

    again = service.execute(str(dem))
    assert again.deduplicated is True
    assert again.match.id == result.match.id
    assert again.parsed is None
