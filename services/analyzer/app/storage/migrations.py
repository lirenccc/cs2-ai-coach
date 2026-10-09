from __future__ import annotations

from pathlib import Path

from .db import Database


def migration_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "migrations"


def migrate(database: Database) -> None:
    migrations = sorted(migration_dir().glob("*.sql"))

    with database.connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        applied = {
            row["version"]
            for row in conn.execute("SELECT version FROM schema_migrations")
        }

        for path in migrations:
            version = path.name
            if version in applied:
                continue
            sql = path.read_text(encoding="utf-8")
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations(version) VALUES (?)",
                (version,),
            )
        conn.commit()
