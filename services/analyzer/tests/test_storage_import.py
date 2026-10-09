from __future__ import annotations

from pathlib import Path

from app.demo.models import (
    NORMALIZATION_SCHEMA_VERSION,
    MatchHeader,
    ParsedDemo,
)
from app.services.import_demo import ImportDemoService
from app.storage.db import Database
from app.storage.demo_repository import DemoRepository
from app.storage.match_repository import MatchRepository
from app.storage.migrations import migrate


class _EmptyParser:
    name = "empty"

    def available(self) -> bool:
        return True

    def version(self) -> str | None:
        return "0"

    def parse(self, demo_path: Path) -> ParsedDemo:
        return ParsedDemo(
            parser_name=self.name,
            parser_version="0",
            normalization_schema_version=NORMALIZATION_SCHEMA_VERSION,
            header=MatchHeader(map_name="de_nuke"),
            roster=[],
            rounds=[],
            kills=[],
            damages=[],
            source_path=str(demo_path),
        )


def test_migration_is_idempotent_and_import_deduplicates(tmp_path: Path):
    db = Database(tmp_path / "app.db")
    migrate(db)
    migrate(db)

    service = ImportDemoService(
        DemoRepository(db),
        MatchRepository(db),
        _EmptyParser(),
        extract_root=tmp_path / "extracted",
    )
    demo = tmp_path / "same.dem"
    demo.write_bytes(b"PBDEMS2\x00same content")

    first = service.execute(str(demo))
    second = service.execute(str(demo))

    assert first.deduplicated is False
    assert second.deduplicated is True
    assert first.record.id == second.record.id
    assert first.record.sha256 == second.record.sha256
    assert first.resolved.demo_path == demo.resolve()
    assert first.match.parse_status == "completed"
    assert first.match.map_name == "de_nuke"

    with db.connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS n FROM demos").fetchone()["n"]
        matches = conn.execute("SELECT COUNT(*) AS n FROM matches").fetchone()["n"]
        migrations = conn.execute(
            "SELECT COUNT(*) AS n FROM schema_migrations"
        ).fetchone()["n"]

    assert count == 1
    assert matches == 1
    assert migrations >= 2
