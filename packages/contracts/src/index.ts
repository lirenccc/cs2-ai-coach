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
