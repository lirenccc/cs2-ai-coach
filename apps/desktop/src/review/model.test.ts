import { describe, expect, it } from "vitest";
import { SYNTHETIC_MATCH_REVIEW } from "./fixtures/syntheticReview";
import {
  assertReviewShape,
  filterIncidents,
  groupTimelineByTick,
  sortIncidents,
} from "./model";
import { incidentTypeLabel, ruleLabel } from "./labels";
import { formatDemoTick } from "./timing";

describe("match review model", () => {
  it("keeps incident ordering stable under shuffle", () => {
    const shuffled = [...SYNTHETIC_MATCH_REVIEW.incidents].reverse();
    expect(sortIncidents(shuffled).map((i) => i.incident_id)).toEqual(
      sortIncidents(SYNTHETIC_MATCH_REVIEW.incidents).map((i) => i.incident_id),
    );
  });

  it("filters by round / player / rule / side / severity", () => {
    const filtered = filterIncidents(SYNTHETIC_MATCH_REVIEW.incidents, {
      roundId: "r1",
      playerIdentityId: "pid_ct1",
      ruleId: "R001",
      side: "ct",
      severity: 3,
    });
    expect(filtered).toHaveLength(1);
    expect(filtered[0]?.incident_id).toBe("inc_r001_a");
  });

  it("does not treat unresolved evaluations as incidents", () => {
    expect(
      SYNTHETIC_MATCH_REVIEW.incidents.every((i) => i.status === "candidate"),
    ).toBe(true);
    expect(SYNTHETIC_MATCH_REVIEW.unresolved_evaluations.length).toBeGreaterThan(
      0,
    );
    expect(
      SYNTHETIC_MATCH_REVIEW.incidents.some((i) =>
        i.incident_id.includes("unresolved"),
      ),
    ).toBe(false);
  });

  it("groups same-tick timeline events without inventing chronology", () => {
    const groups = groupTimelineByTick(SYNTHETIC_MATCH_REVIEW.timeline_events);
    const same = groups.find((group) => group.demoTick === 200);
    expect(same?.events.length).toBeGreaterThan(1);
    const ids = same?.events.map((event) => event.event_id) ?? [];
    expect(ids).toEqual([...ids].sort());
  });

  it("keeps R003 non-blaming candidate label", () => {
    expect(ruleLabel("R003")).toBe("Advantage Loss Candidate");
    expect(incidentTypeLabel("ADVANTAGE_LOSS_CANDIDATE")).toBe(
      "Advantage Loss Candidate",
    );
    expect(incidentTypeLabel("ADVANTAGE_LOSS_CANDIDATE").toLowerCase()).not.toContain(
      "throw",
    );
  });

  it("formats ticks using supplied tick rate only", () => {
    expect(formatDemoTick(256, 128)).toContain("128 Hz");
    expect(formatDemoTick(256, 128)).toContain("~2.0s");
    expect(formatDemoTick(256, null)).toBe("tick 256");
    expect(formatDemoTick(256, undefined)).toBe("tick 256");
    // Must not hard-code 64 Hz when rate is unknown.
    expect(formatDemoTick(256, null)).not.toContain("64");
  });

  it("rejects malformed review payloads", () => {
    expect(() => assertReviewShape(null)).toThrow(/MALFORMED_REVIEW/);
    expect(() => assertReviewShape({ schema_version: "1" })).toThrow(
      /MALFORMED_REVIEW/,
    );
    expect(assertReviewShape(SYNTHETIC_MATCH_REVIEW).match.match_id).toBe(
      "match_review_synth",
    );
  });

  it("uses player identity ids as keys, not display names", () => {
    const keys = SYNTHETIC_MATCH_REVIEW.players.map((p) => p.player_identity_id);
    expect(keys.every((key) => key.startsWith("pid_"))).toBe(true);
    expect(new Set(keys).size).toBe(keys.length);
  });
});
