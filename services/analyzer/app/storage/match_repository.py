from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any
import uuid

from ..demo.models import ParsedDemo
from .db import Database


@dataclass(frozen=True, slots=True)
class MatchRecord:
    id: str
    demo_id: str
    map_name: str | None
    parser_name: str | None
    parser_version: str | None
    normalization_schema_version: str
    parse_status: str
    roster_count: int = 0
    round_count: int = 0
    kill_count: int = 0
    damage_count: int = 0


class MatchRepository:
    def __init__(self, database: Database):
        self.database = database

    def find_by_demo_id(self, demo_id: str) -> MatchRecord | None:
        with self.database.connect() as conn:
            row = conn.execute(
                """
                SELECT id, demo_id, map_name, parser_name, parser_version,
                       normalization_schema_version, parse_status,
                       roster_count, round_count, kill_count, damage_count
                FROM matches
                WHERE demo_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (demo_id,),
            ).fetchone()
        return MatchRecord(**dict(row)) if row else None

    def create_pending(self, demo_id: str) -> MatchRecord:
        record = MatchRecord(
            id=str(uuid.uuid4()),
            demo_id=demo_id,
            map_name=None,
            parser_name=None,
            parser_version=None,
            normalization_schema_version="1",
            parse_status="pending",
        )
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO matches(
                    id, demo_id, map_name, parser_name, parser_version,
                    normalization_schema_version, parse_status
                ) VALUES (?, ?, NULL, NULL, NULL, ?, ?)
                """,
                (
                    record.id,
                    record.demo_id,
                    record.normalization_schema_version,
                    record.parse_status,
                ),
            )
            conn.commit()
        return record

    def save_parsed(self, match_id: str, parsed: ParsedDemo) -> MatchRecord:
        payload = parsed.to_dict()
        with self.database.connect() as conn:
            conn.execute(
                """
                UPDATE matches
                SET map_name = ?,
                    parser_name = ?,
                    parser_version = ?,
                    normalization_schema_version = ?,
                    parse_status = 'completed',
                    patch_version = ?,
                    tick_rate = ?,
                    roster_count = ?,
                    round_count = ?,
                    kill_count = ?,
                    damage_count = ?,
                    parsed_json = ?,
                    parsed_at = CURRENT_TIMESTAMP,
                    error_code = NULL,
                    error_message = NULL
                WHERE id = ?
                """,
                (
                    parsed.header.map_name,
                    parsed.parser_name,
                    parsed.parser_version,
                    parsed.normalization_schema_version,
                    parsed.header.patch_version,
                    parsed.header.tick_rate,
                    len(parsed.roster),
                    len(parsed.rounds),
                    len(parsed.kills),
                    len(parsed.damages),
                    json.dumps(payload, ensure_ascii=False),
                    match_id,
                ),
            )
            conn.commit()
            row = conn.execute(
                """
                SELECT id, demo_id, map_name, parser_name, parser_version,
                       normalization_schema_version, parse_status,
                       roster_count, round_count, kill_count, damage_count
                FROM matches WHERE id = ?
                """,
                (match_id,),
            ).fetchone()
        return MatchRecord(**dict(row))

    def save_failed(
        self,
        match_id: str,
        *,
        error_code: str,
        error_message: str,
        parser_name: str | None = None,
        parser_version: str | None = None,
    ) -> MatchRecord:
        with self.database.connect() as conn:
            conn.execute(
                """
                UPDATE matches
                SET parse_status = 'failed',
                    parser_name = COALESCE(?, parser_name),
                    parser_version = COALESCE(?, parser_version),
                    error_code = ?,
                    error_message = ?,
                    parsed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (parser_name, parser_version, error_code, error_message, match_id),
            )
            conn.commit()
            row = conn.execute(
                """
                SELECT id, demo_id, map_name, parser_name, parser_version,
                       normalization_schema_version, parse_status,
                       roster_count, round_count, kill_count, damage_count
                FROM matches WHERE id = ?
                """,
                (match_id,),
            ).fetchone()
        return MatchRecord(**dict(row))

    def load_parsed_json(self, match_id: str) -> dict[str, Any] | None:
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT parsed_json FROM matches WHERE id = ?",
                (match_id,),
            ).fetchone()
        if not row or row["parsed_json"] is None:
            return None
        return json.loads(row["parsed_json"])
