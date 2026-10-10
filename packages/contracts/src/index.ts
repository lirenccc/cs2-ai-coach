/** Shared domain contracts. Schemas grow in later milestones. */

export const CONTRACTS_SCHEMA_VERSION = "0.1.0";

export type JobStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
  | "interrupted";

export interface BootstrapInfo {
  product: "cs2-ai-coach";
  schemaVersion: string;
}

export interface ParserHealth {
  name: string;
  available: boolean;
  version?: string | null;
}

export interface AnalyzerHealth {
  status: string;
  version: string;
  database: string;
  parser: ParserHealth;
}

/** Stable bridge errors returned by Tauri commands (never includes session token). */
export type BridgeErrorCode =
  | "SIDECAR_NOT_READY"
  | "SIDECAR_START_TIMEOUT"
  | "SIDECAR_CRASHED"
  | "SIDECAR_UNAUTHORIZED"
  | "SIDECAR_REQUEST_TIMEOUT"
  | "SIDECAR_UNAVAILABLE"
  | "SIDECAR_REQUEST_FAILED"
  | "SIDECAR_CONFIG"
  | "SIDECAR_SPAWN_FAILED"
  | "SIDECAR_MALFORMED_RESPONSE"
  | "MATCH_NOT_FOUND"
  | "MATCH_NOT_PARSED"
  | "MATCH_ID_INVALID";

export interface BridgeError {
  code: BridgeErrorCode | string;
  message: string;
  retryable: boolean;
}

export type SidecarStatus =
  | "starting"
  | "ready"
  | "crashed"
  | "stopped"
  | "failed";

export interface DesktopHealth {
  app: string;
  version: string;
  platform: string;
}

export interface ImportDemoResponse {
  demo_id: string;
  match_id: string;
  sha256: string;
  original_path: string;
  deduplicated: boolean;
  parse_status: string;
  map_name?: string | null;
  parser_name?: string | null;
  parser_version?: string | null;
  roster_count: number;
  round_count: number;
  kill_count: number;
  damage_count: number;
}

/** Stable person identity (Steam when valid). Not a demo-local controller. */
export interface PlayerIdentity {
  id: string;
  steamid64?: string | null;
  displayNameLatest?: string | null;
}

/** Demo-local controller/userid interval. */
export interface ControllerSession {
  id: string;
  matchId: string;
  userid: number;
  playerIdentityId?: string | null;
  connectedDemoTick?: number | null;
  disconnectedDemoTick?: number | null;
  isBot: boolean;
  isHltv: boolean;
}

/** One in-world pawn/life interval. */
export interface PawnLife {
  id: string;
  matchId: string;
  controllerSessionId?: string | null;
  pawnHandle: number;
  spawnDemoTick?: number | null;
  deathDemoTick?: number | null;
}

/** Offline Match Review projection (analyzer-authoritative; snake_case wire format). */
export const MATCH_REVIEW_SCHEMA_VERSION = "1.0.0";

export interface MatchReviewMatch {
  match_id: string;
  map_name?: string | null;
  parse_status: string;
  tick_rate?: number | null;
  parser_name?: string | null;
  parser_version?: string | null;
  round_count: number;
  kill_count: number;
  roster_count: number;
}

export interface MatchReviewPlayer {
  player_identity_id: string;
  display_name?: string | null;
  is_bot?: boolean;
}

export interface MatchReviewRound {
  round_id: string;
  round_number: number;
  start_demo_tick?: number | null;
  freeze_end_demo_tick?: number | null;
  end_demo_tick?: number | null;
  winner_side?: string | null;
  round_end_reason?: string | null;
}

export type MatchReviewTimelineEventType =
  | "round_freeze_end"
  | "round_end"
  | "player_death"
  | "bomb_planted"
  | "bomb_defused"
  | "bomb_exploded"
  | "incident_anchor"
  | string;

export interface MatchReviewTimelineEvent {
  event_id: string;
  event_type: MatchReviewTimelineEventType;
  demo_tick: number;
  round_id: string;
  round_number: number;
  player_identity_id?: string | null;
  side?: string | null;
  fields: Record<string, unknown>;
}

export interface MatchReviewEvidence {
  evidence_id: string;
  kind: string;
  label: string;
  demo_tick?: number | null;
  ref?: string | null;
  name?: string | null;
  value?: unknown;
  unit?: string | null;
  certainty?: string | null;
}

export interface MatchReviewIncident {
  incident_id: string;
  rule_id: string;
  rule_version: string;
  incident_type: string;
  round_id: string;
  round_number: number;
  focus_player_id?: string | null;
  focus_side?: string | null;
  start_demo_tick: number;
  anchor_demo_tick: number;
  end_demo_tick: number;
  severity: number;
  confidence: number;
  metrics: Record<string, unknown>;
  evidence: MatchReviewEvidence[];
  status: string;
  thresholds_version?: string | null;
  capture_hint?: Record<string, unknown>;
}

export interface AnalysisCoverageReason {
  reason_code: string;
  count: number;
}

export interface AnalysisCoverageRule {
  rule_id: string;
  rule_version: string;
  matched: number;
  unresolved: number;
  outcome: string;
  unresolved_reasons: AnalysisCoverageReason[];
}

export interface MatchReviewUnresolved {
  rule_id: string;
  round_id: string;
  round_number: number;
  subject: string;
  reason: string;
  reason_code: string;
  certainty: string;
}

export interface MatchReview {
  schema_version: string;
  rule_engine_contract_version: string;
  thresholds_version: string;
  match: MatchReviewMatch;
  players: MatchReviewPlayer[];
  rounds: MatchReviewRound[];
  timeline_events: MatchReviewTimelineEvent[];
  incidents: MatchReviewIncident[];
  analysis_coverage: AnalysisCoverageRule[];
  unresolved_evaluations: MatchReviewUnresolved[];
}
