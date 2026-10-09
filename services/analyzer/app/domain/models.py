from __future__ import annotations

from pydantic import BaseModel, Field


class ParserHealth(BaseModel):
    name: str
    available: bool
    version: str | None = None


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    database: str
    parser: ParserHealth


class ShutdownResponse(BaseModel):
    status: str = "shutting_down"


class ImportDemoRequest(BaseModel):
    path: str = Field(min_length=1, max_length=32767)


class ImportDemoResponse(BaseModel):
    demo_id: str
    match_id: str
    sha256: str
    original_path: str
    deduplicated: bool
    parse_status: str
    map_name: str | None = None
    parser_name: str | None = None
    parser_version: str | None = None
    roster_count: int = 0
    round_count: int = 0
    kill_count: int = 0
    damage_count: int = 0
