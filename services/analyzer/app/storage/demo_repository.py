from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import uuid

from .db import Database


@dataclass(frozen=True, slots=True)
class DemoRecord:
    id: str
    sha256: str
    original_path: str


class DemoRepository:
    def __init__(self, database: Database):
        self.database = database

    def find_by_sha256(self, digest: str) -> DemoRecord | None:
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT id, sha256, original_path FROM demos WHERE sha256 = ?",
                (digest,),
            ).fetchone()
        return DemoRecord(**dict(row)) if row else None

    def create(self, digest: str, original_path: Path, size_bytes: int) -> DemoRecord:
        record = DemoRecord(
            id=str(uuid.uuid4()),
            sha256=digest,
            original_path=str(original_path),
        )
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO demos(id, sha256, original_path, size_bytes)
                VALUES (?, ?, ?, ?)
                """,
                (record.id, record.sha256, record.original_path, size_bytes),
            )
            conn.commit()
        return record
