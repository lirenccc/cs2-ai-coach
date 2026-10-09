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
  | "SIDECAR_SPAWN_FAILED";

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
