import { describe, expect, it } from "vitest";
import type { ViewIncidentInCs2Result } from "@cs2-ai-coach/contracts";
import {
  applyReplayFailure,
  applyReplaySuccess,
  beginReplayRequest,
  shouldApplyReplayResult,
} from "./replayAction";

const sampleResult = (incidentId: string): ViewIncidentInCs2Result => ({
  phase: "Playing",
  match_id: "m1",
  incident_id: incidentId,
  rule_id: "R001",
  seek_demo_tick: 100,
  anchor_demo_tick: 200,
  requested_demo_tick: 100,
  command_delivery_ok: true,
  timescale: 0.5,
  pov_auto_selected: false,
  notes: ["POV not automatically selected yet"],
  demo_sha256_prefix: "abcdef012345",
});

describe("replayAction concurrency", () => {
  it("begins Preparing with stable incident id only", () => {
    const { requestId, state } = beginReplayRequest(0, "inc_a");
    expect(requestId).toBe(1);
    expect(state).toEqual({
      phase: "Preparing",
      requestId: 1,
      incidentId: "inc_a",
    });
    expect(JSON.stringify(state)).not.toContain("netcon");
    expect(JSON.stringify(state)).not.toContain("demo_gototick");
  });

  it("ignores late results from superseded requests", () => {
    const first = beginReplayRequest(0, "inc_a");
    const second = beginReplayRequest(first.requestId, "inc_b");
    expect(shouldApplyReplayResult(second.state, first.requestId)).toBe(false);

    const afterLate = applyReplaySuccess(
      second.state,
      first.requestId,
      sampleResult("inc_a"),
    );
    expect(afterLate.phase).toBe("Preparing");
    if (afterLate.phase === "Preparing") {
      expect(afterLate.incidentId).toBe("inc_b");
    }

    const afterCurrent = applyReplaySuccess(
      second.state,
      second.requestId,
      sampleResult("inc_b"),
    );
    expect(afterCurrent.phase).toBe("Playing");
    if (afterCurrent.phase === "Playing") {
      expect(afterCurrent.incidentId).toBe("inc_b");
    }
  });

  it("keeps failure scoped to the active request id", () => {
    const first = beginReplayRequest(0, "inc_a");
    const second = beginReplayRequest(first.requestId, "inc_b");
    const failed = applyReplayFailure(
      second.state,
      first.requestId,
      "inc_a",
      "NETCON_CONNECTION_LOST",
      "gone",
    );
    expect(failed.phase).toBe("Preparing");
  });
});
