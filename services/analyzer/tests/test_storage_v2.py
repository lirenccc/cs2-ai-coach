from __future__ import annotations

from pathlib import Path
import sqlite3
import uuid

import pytest

from app.demo.models import (
    NORMALIZATION_SCHEMA_VERSION,
    DamageRow,
    KillRow,
    MatchHeader,
    ParsedDemo,
    PlayerRosterEntry,
    RoundRow,
    SelectedTickRow,
)
from app.domain.identity import ControllerSession, PawnLife
from app.domain.match_events import KillEventRecord, RoundMarker, RoundRecord
from app.errors import AppError
from app.services.import_demo import ImportDemoService
from app.storage.db import Database
from app.storage.demo_repository import DemoRepository
from app.storage.event_repository import EventRepository
from app.storage.identity_repository import IdentityRepository
from app.storage.match_repository import MatchRepository
from app.storage.migrations import migrate, migration_dir
from app.storage.persist_parsed import PersistParsedDemoService
from app.storage.round_repository import RoundRepository
from app.storage.schema_versions import STORAGE_SCHEMA_VERSION, STRUCTURAL_PROBE_VERSION
from app.storage.tick_store import JsonTickStore


def _apply_sql_files(db_path: Path, names: list[str]) -> None:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    root = migration_dir()
    for name in names:
        sql = (root / name).read_text(encoding="utf-8")
        conn.executescript(sql)
        conn.execute("INSERT INTO schema_migrations(version) VALUES (?)", (name,))
    conn.commit()
    conn.close()


def _seed_match(database: Database) -> tuple[str, str]:
    demo_id = str(uuid.uuid4())
    match_id = str(uuid.uuid4())
    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO demos(id, sha256, original_path, size_bytes)
            VALUES (?, ?, ?, ?)
            """,
            (demo_id, "a" * 64, "C:/demos/seed.dem", 128),
        )
        conn.execute(
            """
            INSERT INTO matches(
                id, demo_id, map_name, parser_name, parser_version,
                normalization_schema_version, parse_status
            ) VALUES (?, ?, 'de_dust2', 'fake', '1.0', ?, 'completed')
            """,
            (match_id, demo_id, NORMALIZATION_SCHEMA_VERSION),
        )
        conn.commit()
    return demo_id, match_id


def test_fresh_database_migration_reaches_storage_v2(tmp_path: Path) -> None:
    db = Database(tmp_path / "fresh.db")
    migrate(db)
    with db.connect() as conn:
        versions = {
            row["version"]
            for row in conn.execute("SELECT version FROM schema_migrations")
        }
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(matches)")
        }
    assert "001_init.sql" in versions
    assert "002_match_parsed.sql" in versions
    assert "003_storage_v2.sql" in versions
    assert {
        "player_identities",
        "controller_sessions",
        "pawn_lives",
        "rounds",
        "round_markers",
        "kill_events",
        "damage_events",
        "grenade_events",
    } <= tables
    assert {
        "structural_probe_version",
        "build_num",
        "server_start_tick",
        "storage_schema_version",
        "parser_name",
        "parser_version",
        "normalization_schema_version",
    } <= cols


def test_upgrade_from_v0_1_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "v01.db"
    _apply_sql_files(db_path, ["001_init.sql", "002_match_parsed.sql"])
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO demos(id, sha256, original_path, size_bytes)
        VALUES ('demo-1', ?, 'C:/a.dem', 10)
        """,
        ("b" * 64,),
    )
    conn.execute(
        """
        INSERT INTO matches(
            id, demo_id, map_name, parser_name, parser_version,
            normalization_schema_version, parse_status
        ) VALUES ('match-1', 'demo-1', 'de_nuke', 'old', '0.1', '1', 'completed')
        """
    )
    conn.commit()
    conn.close()

    db = Database(db_path)
    migrate(db)
    migrate(db)

    with db.connect() as conn:
        versions = {
            row["version"]
            for row in conn.execute("SELECT version FROM schema_migrations")
        }
        row = conn.execute(
            """
            SELECT storage_schema_version, structural_probe_version, map_name
            FROM matches WHERE id = 'match-1'
            """
        ).fetchone()
        # Existing row keeps data; new columns get defaults/nulls.
        assert row["map_name"] == "de_nuke"
        assert row["storage_schema_version"] == "2"
    assert "003_storage_v2.sql" in versions


def test_migrations_are_idempotent_when_run_twice(tmp_path: Path) -> None:
    db = Database(tmp_path / "twice.db")
    migrate(db)
    migrate(db)
    with db.connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS n FROM schema_migrations").fetchone()[
            "n"
        ]
    assert count == 3


def test_duplicate_demo_sha256_rejected(tmp_path: Path) -> None:
    db = Database(tmp_path / "dedupe.db")
    migrate(db)
    repo = DemoRepository(db)
    repo.create("c" * 64, Path("C:/one.dem"), 11)
    with pytest.raises(Exception):
        repo.create("c" * 64, Path("C:/two.dem"), 12)


def test_player_identity_with_multiple_controller_sessions(tmp_path: Path) -> None:
    db = Database(tmp_path / "identity.db")
    migrate(db)
    _, match_id = _seed_match(db)
    identities = IdentityRepository(db)
    person = identities.upsert_player_identity(
        steamid64="76561198000000001",
        display_name="Alice",
    )
    first = identities.create_controller_session(
        ControllerSession(
            id=str(uuid.uuid4()),
            match_id=match_id,
            userid=2,
            player_identity_id=person.id,
            connected_demo_tick=10,
            disconnected_demo_tick=100,
            is_bot=False,
            is_hltv=False,
        )
    )
    second = identities.create_controller_session(
        ControllerSession(
            id=str(uuid.uuid4()),
            match_id=match_id,
            userid=7,
            player_identity_id=person.id,
            connected_demo_tick=200,
            disconnected_demo_tick=None,
            is_bot=False,
            is_hltv=False,
        )
    )
    sessions = identities.list_controller_sessions(match_id)
    assert {s.id for s in sessions} == {first.id, second.id}
    assert all(s.player_identity_id == person.id for s in sessions)


def test_bot_controller_without_steamid64(tmp_path: Path) -> None:
    db = Database(tmp_path / "bot.db")
    migrate(db)
    _, match_id = _seed_match(db)
    identities = IdentityRepository(db)
    bot = identities.create_controller_session(
        ControllerSession(
            id=str(uuid.uuid4()),
            match_id=match_id,
            userid=12,
            player_identity_id=None,
            connected_demo_tick=50,
            disconnected_demo_tick=None,
            is_bot=True,
            is_hltv=False,
        )
    )
    assert bot.player_identity_id is None
    assert bot.is_bot is True
    with db.connect() as conn:
        steam_nulls = conn.execute(
            "SELECT COUNT(*) AS n FROM player_identities WHERE steamid64 IS NULL"
        ).fetchone()["n"]
    assert steam_nulls == 0


def test_controller_session_multiple_pawn_lives(tmp_path: Path) -> None:
    db = Database(tmp_path / "pawns.db")
    migrate(db)
    _, match_id = _seed_match(db)
    identities = IdentityRepository(db)
    session = identities.create_controller_session(
        ControllerSession(
            id=str(uuid.uuid4()),
            match_id=match_id,
            userid=3,
            player_identity_id=None,
            connected_demo_tick=1,
            disconnected_demo_tick=None,
            is_bot=False,
            is_hltv=False,
        )
    )
    life_a = identities.create_pawn_life(
        PawnLife(
            id=str(uuid.uuid4()),
            match_id=match_id,
            controller_session_id=session.id,
            pawn_handle=1001,
            spawn_demo_tick=10,
            death_demo_tick=40,
        )
    )
    life_b = identities.create_pawn_life(
        PawnLife(
            id=str(uuid.uuid4()),
            match_id=match_id,
            controller_session_id=session.id,
            pawn_handle=1002,
            spawn_demo_tick=45,
            death_demo_tick=90,
        )
    )
    lives = identities.list_pawn_lives(match_id)
    assert {life.id for life in lives} == {life_a.id, life_b.id}
    assert all(life.controller_session_id == session.id for life in lives)


def test_multiple_deaths_same_controller_same_round(tmp_path: Path) -> None:
    db = Database(tmp_path / "deaths.db")
    migrate(db)
    _, match_id = _seed_match(db)
    rounds = RoundRepository(db)
    round_id = str(uuid.uuid4())
    rounds.replace_rounds(
        match_id,
        [
            RoundRecord(
                id=round_id,
                match_id=match_id,
                round_no=1,
                freeze_end_demo_tick=10,
                end_demo_tick=200,
                end_marker_type="round_officially_ended",
            )
        ],
        [
            RoundMarker(
                id=str(uuid.uuid4()),
                match_id=match_id,
                marker_type="round_freeze_end",
                demo_tick=10,
                server_tick=None,
                sequence_index=1,
            )
        ],
    )
    events = EventRepository(db)
    events.replace_combat_events(
        match_id,
        kills=[
            KillEventRecord(
                event_id="kill:a",
                match_id=match_id,
                round_id=round_id,
                demo_tick=20,
                server_tick=3800,
                victim_userid=5,
                victim_pawn_handle=11,
                attacker_userid=6,
                attacker_pawn_handle=12,
                assister_userid=None,
                assister_pawn_handle=None,
                weapon="ak47",
                headshot=True,
                penetrated=False,
                source_event_id="kill:a",
                source_parser="fake",
            ),
            KillEventRecord(
                event_id="kill:b",
                match_id=match_id,
                round_id=round_id,
                demo_tick=80,
                server_tick=3860,
                victim_userid=5,
                victim_pawn_handle=13,
                attacker_userid=6,
                attacker_pawn_handle=12,
                assister_userid=None,
                assister_pawn_handle=None,
                weapon="ak47",
                headshot=False,
                penetrated=False,
                source_event_id="kill:b",
                source_parser="fake",
            ),
        ],
        damages=[],
        grenades=[],
    )
    kills = events.list_kills(match_id)
    assert len(kills) == 2
    assert {k.event_id for k in kills} == {"kill:a", "kill:b"}
    assert all(k.victim_userid == 5 for k in kills)
    assert all(k.round_id == round_id for k in kills)


def test_nullable_and_distinct_tick_domains(tmp_path: Path) -> None:
    db = Database(tmp_path / "ticks.db")
    migrate(db)
    _, match_id = _seed_match(db)
    events = EventRepository(db)
    events.replace_combat_events(
        match_id,
        kills=[
            KillEventRecord(
                event_id="kill:null-server",
                match_id=match_id,
                round_id=None,
                demo_tick=100,
                server_tick=None,
                victim_userid=1,
                victim_pawn_handle=2,
                attacker_userid=None,
                attacker_pawn_handle=None,
                assister_userid=None,
                assister_pawn_handle=None,
                weapon="world",
                headshot=False,
                penetrated=False,
                source_event_id="kill:null-server",
                source_parser="fake",
            ),
            KillEventRecord(
                event_id="kill:dual",
                match_id=match_id,
                round_id=None,
                demo_tick=101,
                server_tick=3880,
                victim_userid=1,
                victim_pawn_handle=3,
                attacker_userid=4,
                attacker_pawn_handle=5,
                assister_userid=None,
                assister_pawn_handle=None,
                weapon="awp",
                headshot=True,
                penetrated=False,
                source_event_id="kill:dual",
                source_parser="fake",
            ),
        ],
        damages=[],
        grenades=[],
    )
    kills = {row.event_id: row for row in events.list_kills(match_id)}
    assert kills["kill:null-server"].server_tick is None
    assert kills["kill:null-server"].demo_tick == 100
    assert kills["kill:dual"].demo_tick == 101
    assert kills["kill:dual"].server_tick == 3880
    assert kills["kill:dual"].server_tick - kills["kill:dual"].demo_tick == 3779


def test_final_round_fallback_marker(tmp_path: Path) -> None:
    db = Database(tmp_path / "rounds.db")
    migrate(db)
    _, match_id = _seed_match(db)
    persist = PersistParsedDemoService(
        IdentityRepository(db),
        RoundRepository(db),
        EventRepository(db),
    )
    parsed = ParsedDemo(
        parser_name="fake",
        parser_version="1",
        normalization_schema_version=NORMALIZATION_SCHEMA_VERSION,
        header=MatchHeader(map_name="de_dust2", server_start_tick=3779),
        roster=[],
        rounds=[
            RoundRow(round_number=1, freeze_end_tick=10, end_tick=50),
            RoundRow(round_number=2, freeze_end_tick=60, end_tick=120),
        ],
        kills=[],
        damages=[],
        event_counts={
            "round_freeze_end": 2,
            "round_officially_ended": 1,
            "cs_win_panel_match": 1,
        },
    )
    persist.persist(match_id, parsed)
    rounds = RoundRepository(db).list_rounds(match_id)
    markers = RoundRepository(db).list_markers(match_id)
    assert rounds[0].end_marker_type == "round_officially_ended"
    assert rounds[1].end_marker_type == "cs_win_panel_match"
    assert sum(1 for m in markers if m.marker_type == "round_freeze_end") == 2
    assert sum(1 for m in markers if m.marker_type == "round_officially_ended") == 1
    assert sum(1 for m in markers if m.marker_type == "cs_win_panel_match") == 1


def test_parser_probe_schema_versions_persisted(tmp_path: Path) -> None:
    db = Database(tmp_path / "versions.db")
    migrate(db)

    class _Parser:
        name = "fake"

        def available(self) -> bool:
            return True

        def version(self) -> str | None:
            return "9.9.9"

        def parse(self, demo_path: Path) -> ParsedDemo:
            return ParsedDemo(
                parser_name=self.name,
                parser_version="9.9.9",
                normalization_schema_version=NORMALIZATION_SCHEMA_VERSION,
                header=MatchHeader(
                    map_name="de_dust2",
                    patch_version="14189",
                    build_num="10924",
                    server_start_tick=3779,
                ),
                roster=[],
                rounds=[],
                kills=[],
                damages=[],
            )

    demo = tmp_path / "v.dem"
    demo.write_bytes(b"PBDEMS2\x00version-check")
    result = ImportDemoService(
        DemoRepository(db),
        MatchRepository(db),
        _Parser(),
        extract_root=tmp_path / "extracted",
    ).execute(str(demo))

    match = MatchRepository(db).get(result.match.id)
    assert match is not None
    assert match.parser_name == "fake"
    assert match.parser_version == "9.9.9"
    assert match.normalization_schema_version == NORMALIZATION_SCHEMA_VERSION
    assert match.structural_probe_version == STRUCTURAL_PROBE_VERSION
    assert match.storage_schema_version == STORAGE_SCHEMA_VERSION
    assert match.patch_version == "14189"
    assert match.build_num == "10924"
    assert match.server_start_tick == 3779
    with db.connect() as conn:
        sha = conn.execute(
            "SELECT sha256 FROM demos WHERE id = ?",
            (result.record.id,),
        ).fetchone()["sha256"]
    assert len(sha) == 64


def test_foreign_key_cascade_on_match_delete(tmp_path: Path) -> None:
    db = Database(tmp_path / "cascade.db")
    migrate(db)
    _, match_id = _seed_match(db)
    identities = IdentityRepository(db)
    session = identities.create_controller_session(
        ControllerSession(
            id=str(uuid.uuid4()),
            match_id=match_id,
            userid=1,
            player_identity_id=None,
            connected_demo_tick=1,
            disconnected_demo_tick=None,
            is_bot=False,
            is_hltv=False,
        )
    )
    identities.create_pawn_life(
        PawnLife(
            id=str(uuid.uuid4()),
            match_id=match_id,
            controller_session_id=session.id,
            pawn_handle=9,
            spawn_demo_tick=1,
            death_demo_tick=2,
        )
    )
    RoundRepository(db).replace_rounds(
        match_id,
        [
            RoundRecord(
                id=str(uuid.uuid4()),
                match_id=match_id,
                round_no=1,
                freeze_end_demo_tick=1,
                end_demo_tick=2,
                end_marker_type="round_officially_ended",
            )
        ],
        [],
    )
    EventRepository(db).replace_combat_events(
        match_id,
        kills=[
            KillEventRecord(
                event_id="kill:cascade",
                match_id=match_id,
                round_id=None,
                demo_tick=1,
                server_tick=None,
                victim_userid=1,
                victim_pawn_handle=9,
                attacker_userid=None,
                attacker_pawn_handle=None,
                assister_userid=None,
                assister_pawn_handle=None,
                weapon=None,
                headshot=False,
                penetrated=False,
                source_event_id="kill:cascade",
                source_parser="fake",
            )
        ],
        damages=[],
        grenades=[],
    )
    MatchRepository(db).delete(match_id)
    with db.connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM controller_sessions WHERE match_id = ?",
            (match_id,),
        ).fetchone()["n"] == 0
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM pawn_lives WHERE match_id = ?",
            (match_id,),
        ).fetchone()["n"] == 0
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM rounds WHERE match_id = ?",
            (match_id,),
        ).fetchone()["n"] == 0
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM kill_events WHERE match_id = ?",
            (match_id,),
        ).fetchone()["n"] == 0


def test_invalid_identity_references_are_rejected(tmp_path: Path) -> None:
    db = Database(tmp_path / "badref.db")
    migrate(db)
    _, match_id = _seed_match(db)
    identities = IdentityRepository(db)
    with pytest.raises(AppError) as session_exc:
        identities.create_controller_session(
            ControllerSession(
                id=str(uuid.uuid4()),
                match_id=match_id,
                userid=1,
                player_identity_id="missing-identity",
                connected_demo_tick=None,
                disconnected_demo_tick=None,
                is_bot=False,
                is_hltv=False,
            )
        )
    assert session_exc.value.code == "STORAGE_INVALID_IDENTITY_REF"

    with pytest.raises(AppError) as pawn_exc:
        identities.create_pawn_life(
            PawnLife(
                id=str(uuid.uuid4()),
                match_id=match_id,
                controller_session_id="missing-session",
                pawn_handle=1,
                spawn_demo_tick=None,
                death_demo_tick=None,
            )
        )
    assert pawn_exc.value.code == "STORAGE_INVALID_IDENTITY_REF"

    with pytest.raises(AppError) as kill_exc:
        EventRepository(db).insert_kill(
            KillEventRecord(
                event_id="kill:bad-round",
                match_id=match_id,
                round_id="missing-round",
                demo_tick=1,
                server_tick=None,
                victim_userid=1,
                victim_pawn_handle=1,
                attacker_userid=None,
                attacker_pawn_handle=None,
                assister_userid=None,
                assister_pawn_handle=None,
                weapon=None,
                headshot=False,
                penetrated=False,
                source_event_id="kill:bad-round",
                source_parser="fake",
            )
        )
    assert kill_exc.value.code == "STORAGE_INVALID_IDENTITY_REF"


def test_tick_store_keeps_dense_rows_out_of_sqlite(tmp_path: Path) -> None:
    db = Database(tmp_path / "ticks-store.db")
    migrate(db)
    _, match_id = _seed_match(db)
    store = JsonTickStore(tmp_path / "matches")
    rows = [
        SelectedTickRow(
            demo_tick=10,
            player_id="steam:1",
            steamid64="1",
            x=1.0,
            y=2.0,
            z=3.0,
            health=100.0,
            team="CT",
            is_alive=True,
            selection_reason="round_freeze_end",
        )
    ]
    store.write_ticks(match_id, rows)
    assert store.query(match_id, tick_start=10, tick_end=10)
    with db.connect() as conn:
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert "player_ticks" not in tables
    assert "selected_ticks" not in tables


def test_import_persists_normalized_graph_without_dataframe(tmp_path: Path) -> None:
    db = Database(tmp_path / "import-graph.db")
    migrate(db)

    class _Parser:
        name = "fake"

        def available(self) -> bool:
            return True

        def version(self) -> str | None:
            return "1"

        def parse(self, demo_path: Path) -> ParsedDemo:
            return ParsedDemo(
                parser_name=self.name,
                parser_version="1",
                normalization_schema_version=NORMALIZATION_SCHEMA_VERSION,
                header=MatchHeader(
                    map_name="de_dust2",
                    patch_version="14189",
                    build_num="10924",
                    server_start_tick=3779,
                ),
                roster=[
                    PlayerRosterEntry(
                        player_id="steam:76561198000000001",
                        steamid64="76561198000000001",
                        display_name="Alice",
                        team="CT",
                        userid=2,
                    ),
                    PlayerRosterEntry(
                        player_id="bot:3",
                        steamid64=None,
                        display_name="Bot Mike",
                        team="T",
                        is_bot=True,
                        userid=3,
                    ),
                ],
                rounds=[
                    RoundRow(round_number=1, freeze_end_tick=10, end_tick=100),
                    RoundRow(round_number=2, freeze_end_tick=110, end_tick=200),
                ],
                kills=[
                    KillRow(
                        event_id="kill:1",
                        tick=20,
                        attacker_id="steam:x",
                        victim_id="steam:76561198000000001",
                        weapon="ak47",
                        round_number=1,
                        demo_tick=20,
                        server_tick=3799,
                        victim_userid=2,
                        victim_pawn=501,
                        attacker_userid=3,
                        attacker_pawn=502,
                    ),
                    KillRow(
                        event_id="kill:2",
                        tick=40,
                        attacker_id="steam:x",
                        victim_id="steam:76561198000000001",
                        weapon="ak47",
                        round_number=1,
                        demo_tick=40,
                        server_tick=3819,
                        victim_userid=2,
                        victim_pawn=503,
                        attacker_userid=3,
                        attacker_pawn=502,
                    ),
                ],
                damages=[
                    DamageRow(
                        event_id="damage:1",
                        tick=19,
                        attacker_id="steam:x",
                        victim_id="steam:76561198000000001",
                        hp_damage=20,
                        demo_tick=19,
                        server_tick=None,
                        victim_userid=2,
                        victim_pawn=501,
                    )
                ],
                event_counts={
                    "round_freeze_end": 2,
                    "round_officially_ended": 1,
                    "cs_win_panel_match": 1,
                },
                selected_ticks=[
                    SelectedTickRow(
                        demo_tick=10,
                        player_id="steam:76561198000000001",
                        steamid64="76561198000000001",
                        x=0.0,
                        y=0.0,
                        z=0.0,
                        health=100.0,
                        team="CT",
                        is_alive=True,
                        selection_reason="round_freeze_end",
                    )
                ],
            )

    tick_store = JsonTickStore(tmp_path / "matches")
    demo = tmp_path / "graph.dem"
    demo.write_bytes(b"PBDEMS2\x00graph")
    result = ImportDemoService(
        DemoRepository(db),
        MatchRepository(db),
        _Parser(),
        extract_root=tmp_path / "extracted",
        tick_store=tick_store,
    ).execute(str(demo))

    sessions = IdentityRepository(db).list_controller_sessions(result.match.id)
    assert len(sessions) == 2
    human = next(s for s in sessions if s.userid == 2)
    bot = next(s for s in sessions if s.userid == 3)
    assert human.player_identity_id is not None
    assert bot.is_bot is True
    assert bot.player_identity_id is None

    lives = IdentityRepository(db).list_pawn_lives(result.match.id)
    assert len(lives) == 2
    assert {life.pawn_handle for life in lives} == {501, 503}

    kills = EventRepository(db).list_kills(result.match.id)
    assert len(kills) == 2
    assert all(k.round_id is not None for k in kills)
    damages = EventRepository(db).list_damages(result.match.id)
    assert damages[0].server_tick is None
    assert damages[0].demo_tick == 19

    rounds = RoundRepository(db).list_rounds(result.match.id)
    assert rounds[-1].end_marker_type == "cs_win_panel_match"
    assert tick_store.query(result.match.id)
