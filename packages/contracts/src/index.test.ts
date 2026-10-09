import { describe, expect, it } from "vitest";
import {
  CONTRACTS_SCHEMA_VERSION,
  type AnalyzerHealth,
  type BootstrapInfo,
  type BridgeError,
  type ImportDemoResponse,
} from "./index";

describe("contracts bootstrap", () => {
  it("exposes a versioned bootstrap contract", () => {
    const info: BootstrapInfo = {
      product: "cs2-ai-coach",
      schemaVersion: CONTRACTS_SCHEMA_VERSION,
    };
    expect(info.product).toBe("cs2-ai-coach");
    expect(info.schemaVersion).toMatch(/^\d+\.\d+\.\d+$/);
  });

  it("types the analyzer health and import responses", () => {
    const health: AnalyzerHealth = {
      status: "ok",
      version: "0.1.0",
      database: "runtime/app.db",
      parser: { name: "demoparser2", available: false },
    };
    const imported: ImportDemoResponse = {
      demo_id: "demo-1",
      match_id: "match-1",
      sha256: "abc",
      original_path: "C:/matches/a.dem",
      deduplicated: false,
      parse_status: "completed",
      map_name: "de_dust2",
      parser_name: "awpy+demoparser2",
      roster_count: 10,
      round_count: 18,
      kill_count: 128,
      damage_count: 444,
    };
    expect(health.parser.name).toBe("demoparser2");
    expect(imported.deduplicated).toBe(false);
    expect(imported.match_id).toBe("match-1");

    const bridgeError: BridgeError = {
      code: "SIDECAR_CRASHED",
      message: "analyzer sidecar process exited unexpectedly",
      retryable: true,
    };
    expect(bridgeError.code).toBe("SIDECAR_CRASHED");
    expect(bridgeError.retryable).toBe(true);
  });
});
