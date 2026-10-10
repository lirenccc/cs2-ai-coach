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


class MatchReviewMatch(BaseModel):
    match_id: str
    map_name: str | None = None
    parse_status: str
    tick_rate: float | None = None
    parser_name: str | None = None
    parser_version: str | None = None
    round_count: int = 0
    kill_count: int = 0
    roster_count: int = 0


class MatchReviewPlayer(BaseModel):
    player_identity_id: str
    display_name: str | None = None
    is_bot: bool = False


class MatchReviewRound(BaseModel):
    round_id: str
    round_number: int
    start_demo_tick: int | None = None
    freeze_end_demo_tick: int | None = None
    end_demo_tick: int | None = None
    winner_side: str | None = None
    round_end_reason: str | None = None


class MatchReviewTimelineEvent(BaseModel):
    event_id: str
    event_type: str
    demo_tick: int
    round_id: str
    round_number: int
    player_identity_id: str | None = None
    side: str | None = None
    fields: dict = Field(default_factory=dict)


class MatchReviewEvidence(BaseModel):
    evidence_id: str
    kind: str
    label: str
    demo_tick: int | None = None
    ref: str | None = None
    name: str | None = None
    value: object | None = None
    unit: str | None = None
    certainty: str | None = None


class MatchReviewIncident(BaseModel):
    incident_id: str
    rule_id: str
    rule_version: str
    incident_type: str
    round_id: str
    round_number: int
    focus_player_id: str | None = None
    focus_side: str | None = None
    start_demo_tick: int
    anchor_demo_tick: int
    end_demo_tick: int
    severity: int
    confidence: float
    metrics: dict = Field(default_factory=dict)
    evidence: list[MatchReviewEvidence] = Field(default_factory=list)
    status: str = "candidate"
    thresholds_version: str | None = None
    capture_hint: dict = Field(default_factory=dict)


class AnalysisCoverageReason(BaseModel):
    reason_code: str
    count: int


class AnalysisCoverageRule(BaseModel):
    rule_id: str
    rule_version: str
    matched: int
    unresolved: int
    outcome: str
    unresolved_reasons: list[AnalysisCoverageReason] = Field(default_factory=list)


class MatchReviewUnresolved(BaseModel):
    rule_id: str
    round_id: str
    round_number: int
    subject: str
    reason: str
    reason_code: str
    certainty: str = "unresolved"


class MatchReviewResponse(BaseModel):
    schema_version: str
    rule_engine_contract_version: str
    thresholds_version: str
    match: MatchReviewMatch
    players: list[MatchReviewPlayer]
    rounds: list[MatchReviewRound]
    timeline_events: list[MatchReviewTimelineEvent]
    incidents: list[MatchReviewIncident]
    analysis_coverage: list[AnalysisCoverageRule]
    unresolved_evaluations: list[MatchReviewUnresolved]


class IncidentReplayPlan(BaseModel):
    """Canonical Click-to-CS2 plan. Absolute paths are for native only."""

    version: str
    match_id: str
    incident_id: str
    rule_id: str
    round_id: str
    round_number: int
    start_demo_tick: int
    anchor_demo_tick: int
    end_demo_tick: int
    seek_demo_tick: int
    replay_tick_domain: str = "DemoTick"
    replay_semantics_version: str
    timing_source: str
    verified_tick_rate: float | None = None
    timing_degraded: bool = False
    pre_roll_seconds: float
    settle_policy: str
    settle_debounce_ms: int
    timescale: float
    auto_resume: bool = True
    pov_auto_selected: bool = False
    demo_sha256: str
    demo_source_available: bool = False
    # Consumed only by Tauri; never part of the renderer TypeScript contract.
    demo_source_path: str | None = None
