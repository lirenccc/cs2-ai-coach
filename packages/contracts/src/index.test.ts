import { describe, expect, it } from "vitest";
import {
  CONTRACTS_SCHEMA_VERSION,
  INCIDENT_REPLAY_PLAN_VERSION,
  MATCH_REVIEW_SCHEMA_VERSION,
  REPLAY_SEMANTICS_VERSION,
  type AnalyzerHealth,
  type BootstrapInfo,
  type BridgeError,
  type ControllerSession,
  type ImportDemoResponse,
  type IncidentReplayPlan,
  type MatchReview,
  type PawnLife,
  type PlayerIdentity,
  type ViewIncidentInCs2Result,
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

    const identity: PlayerIdentity = {
      id: "pi-1",
      steamid64: "76561198000000001",
      displayNameLatest: "Alice",
    };
    const session: ControllerSession = {
      id: "cs-1",
      matchId: "match-1",
      userid: 2,
      playerIdentityId: identity.id,
      isBot: false,
      isHltv: false,
    };
    const life: PawnLife = {
      id: "pl-1",
      matchId: "match-1",
      controllerSessionId: session.id,
      pawnHandle: 501,
      deathDemoTick: 40,
    };
    expect(session.playerIdentityId).toBe(identity.id);
    expect(life.controllerSessionId).toBe(session.id);
  });

  it("types the match review projection without sidecar secrets", () => {
    const review: MatchReview = {
      schema_version: MATCH_REVIEW_SCHEMA_VERSION,
      rule_engine_contract_version: "rule-engine-v1-2026-10-10",
      thresholds_version: "rule-thresholds-v1-2026-10-10",
      match: {
        match_id: "match-1",
        map_name: "de_dust2",
        parse_status: "completed",
        tick_rate: 128,
        round_count: 2,
        kill_count: 4,
        roster_count: 10,
      },
      players: [
        {
          player_identity_id: "pid_ct1",
          display_name: "Player_A",
          is_bot: false,
        },
      ],
      rounds: [
        {
          round_id: "r1",
          round_number: 1,
          freeze_end_demo_tick: 100,
          end_demo_tick: 500,
          winner_side: "t",
        },
      ],
      timeline_events: [
        {
          event_id: "kill:1",
          event_type: "player_death",
          demo_tick: 200,
          round_id: "r1",
          round_number: 1,
          player_identity_id: "pid_ct1",
          side: "ct",
          fields: {},
        },
      ],
      incidents: [
        {
          incident_id: "inc_1",
          rule_id: "R003",
          rule_version: "1.0.0",
          incident_type: "ADVANTAGE_LOSS_CANDIDATE",
          round_id: "r1",
          round_number: 1,
          focus_side: "ct",
          start_demo_tick: 300,
          anchor_demo_tick: 500,
          end_demo_tick: 500,
          severity: 3,
          confidence: 1,
          metrics: { peak_advantage: 2 },
          evidence: [
            {
              evidence_id: "ev_1",
              kind: "metric",
              label: "peak advantage",
              name: "peak_advantage",
              value: 2,
            },
          ],
          status: "candidate",
          thresholds_version: "rule-thresholds-v1-2026-10-10",
        },
      ],
      analysis_coverage: [
        {
          rule_id: "R001",
          rule_version: "1.0.0",
          matched: 1,
          unresolved: 1,
          outcome: "matched",
          unresolved_reasons: [
            { reason_code: "TAKEOVER_ATTRIBUTION_UNRESOLVED", count: 1 },
          ],
        },
      ],
      unresolved_evaluations: [
        {
          rule_id: "R001",
          round_id: "r3",
          round_number: 3,
          subject: "pid_ct1",
          reason: "opening_death_crosses_unresolved_takeover",
          reason_code: "TAKEOVER_ATTRIBUTION_UNRESOLVED",
          certainty: "unresolved",
        },
      ],
    };
    expect(review.schema_version).toBe("1.0.0");
    expect(review.incidents[0]?.incident_type).toBe("ADVANTAGE_LOSS_CANDIDATE");
    expect(review.match).not.toHaveProperty("original_path");
    expect(review).not.toHaveProperty("session_token");
  });

  it("types IncidentReplayPlan without private path or NetCon fields", () => {
    const plan: IncidentReplayPlan = {
      version: INCIDENT_REPLAY_PLAN_VERSION,
      match_id: "match-1",
      incident_id: "inc_1",
      rule_id: "R001",
      round_id: "r1",
      round_number: 1,
      start_demo_tick: 300,
      anchor_demo_tick: 500,
      end_demo_tick: 520,
      seek_demo_tick: 300,
      replay_tick_domain: "DemoTick",
      replay_semantics_version: REPLAY_SEMANTICS_VERSION,
      timing_source: "match.tick_rate",
      verified_tick_rate: 128,
      pre_roll_seconds: 5,
      settle_policy: "fixed_debounce_ms",
      settle_debounce_ms: 2000,
      timescale: 0.5,
      auto_resume: true,
      pov_auto_selected: false,
      demo_sha256: "ab".repeat(32),
      demo_source_available: true,
    };
    expect(plan.replay_tick_domain).toBe("DemoTick");
    expect(plan).not.toHaveProperty("demo_source_path");
    expect(plan).not.toHaveProperty("server_tick");
    expect(plan).not.toHaveProperty("netcon_port");
    expect(plan).not.toHaveProperty("session_token");

    const result: ViewIncidentInCs2Result = {
      phase: "Playing",
      match_id: plan.match_id,
      incident_id: plan.incident_id,
      rule_id: plan.rule_id,
      seek_demo_tick: plan.seek_demo_tick,
      anchor_demo_tick: plan.anchor_demo_tick,
      requested_demo_tick: plan.seek_demo_tick,
      command_delivery_ok: true,
      timescale: 0.5,
      pov_auto_selected: false,
      notes: ["POV not automatically selected yet"],
      demo_sha256_prefix: plan.demo_sha256.slice(0, 12),
    };
    expect(result.phase).toBe("Playing");
    expect(result).not.toHaveProperty("demo_source_path");
  });
});
