from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any
import uuid

from ..demo.models import NORMALIZATION_SCHEMA_VERSION, ParsedDemo
from .db import Database
from .schema_versions import STORAGE_SCHEMA_VERSION, STRUCTURAL_PROBE_VERSION


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
    structural_probe_version: str | None = None
    build_num: str | None = None
    server_start_tick: int | None = None
    storage_schema_version: str | None = None
    patch_version: str | None = None


_MATCH_SELECT = """
    SELECT id, demo_id, map_name, parser_name, parser_version,
           normalization_schema_version, parse_status,
           roster_count, round_count, kill_count, damage_count,
           structural_probe_version, build_num, server_start_tick,
           storage_schema_version, patch_version
    FROM matches
"""


def _row_to_record(row: Any) -> MatchRecord:
    return MatchRecord(
        id=row["id"],
        demo_id=row["demo_id"],
        map_name=row["map_name"],
        parser_name=row["parser_name"],
        parser_version=row["parser_version"],
        normalization_schema_version=row["normalization_schema_version"],
        parse_status=row["parse_status"],
        roster_count=row["roster_count"],
        round_count=row["round_count"],
        kill_count=row["kill_count"],
        damage_count=row["damage_count"],
        structural_probe_version=row["structural_probe_version"],
        build_num=row["build_num"],
        server_start_tick=row["server_start_tick"],
        storage_schema_version=row["storage_schema_version"],
        patch_version=row["patch_version"],
    )


class MatchRepository:
    def __init__(self, database: Database):
        self.database = database

    def find_by_demo_id(self, demo_id: str) -> MatchRecord | None:
        with self.database.connect() as conn:
            row = conn.execute(
                f"""
                {_MATCH_SELECT}
                WHERE demo_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (demo_id,),
            ).fetchone()
        return _row_to_record(row) if row else None

    def get(self, match_id: str) -> MatchRecord | None:
        with self.database.connect() as conn:
            row = conn.execute(
                f"{_MATCH_SELECT} WHERE id = ?",
                (match_id,),
            ).fetchone()
        return _row_to_record(row) if row else None

    def create_pending(self, demo_id: str) -> MatchRecord:
        record = MatchRecord(
            id=str(uuid.uuid4()),
            demo_id=demo_id,
            map_name=None,
            parser_name=None,
            parser_version=None,
            normalization_schema_version=NORMALIZATION_SCHEMA_VERSION,
            parse_status="pending",
            structural_probe_version=STRUCTURAL_PROBE_VERSION,
            storage_schema_version=STORAGE_SCHEMA_VERSION,
        )
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO matches(
                    id, demo_id, map_name, parser_name, parser_version,
                    normalization_schema_version, parse_status,
                    structural_probe_version, storage_schema_version
                ) VALUES (?, ?, NULL, NULL, NULL, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.demo_id,
                    record.normalization_schema_version,
                    record.parse_status,
                    record.structural_probe_version,
                    record.storage_schema_version,
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
                    build_num = ?,
                    server_start_tick = ?,
                    structural_probe_version = ?,
                    storage_schema_version = ?,
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
                    parsed.header.build_num,
                    parsed.header.server_start_tick,
                    STRUCTURAL_PROBE_VERSION,
                    STORAGE_SCHEMA_VERSION,
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
                f"{_MATCH_SELECT} WHERE id = ?",
                (match_id,),
            ).fetchone()
        return _row_to_record(row)

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
                    structural_probe_version = COALESCE(structural_probe_version, ?),
                    storage_schema_version = COALESCE(storage_schema_version, ?),
                    error_code = ?,
                    error_message = ?,
                    parsed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    parser_name,
                    parser_version,
                    STRUCTURAL_PROBE_VERSION,
                    STORAGE_SCHEMA_VERSION,
                    error_code,
                    error_message,
                    match_id,
                ),
            )
            conn.commit()
            row = conn.execute(
                f"{_MATCH_SELECT} WHERE id = ?",
                (match_id,),
            ).fetchone()
        return _row_to_record(row)

    def load_parsed_json(self, match_id: str) -> dict[str, Any] | None:
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT parsed_json FROM matches WHERE id = ?",
                (match_id,),
            ).fetchone()
        if not row or row["parsed_json"] is None:
            return None
        return json.loads(row["parsed_json"])

    def delete(self, match_id: str) -> None:
        with self.database.connect() as conn:
            conn.execute("DELETE FROM matches WHERE id = ?", (match_id,))
            conn.commit()
