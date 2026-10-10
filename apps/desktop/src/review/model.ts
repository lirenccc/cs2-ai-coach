import type {
  MatchReview,
  MatchReviewIncident,
  MatchReviewTimelineEvent,
} from "@cs2-ai-coach/contracts";

export type RoundFilter = "all" | string;
export type RuleFilter = "all" | "R001" | "R002" | "R003";
export type SideFilter = "all" | "ct" | "t";
export type SeverityFilter = "all" | 1 | 2 | 3 | 4 | 5;

export interface ReviewFilters {
  roundId: RoundFilter;
  playerIdentityId: string | "all";
  ruleId: RuleFilter;
  side: SideFilter;
  severity: SeverityFilter;
}

export const DEFAULT_REVIEW_FILTERS: ReviewFilters = {
  roundId: "all",
  playerIdentityId: "all",
  ruleId: "all",
  side: "all",
  severity: "all",
};

/** Canonical incident order — mirrors analyzer sort_incidents. */
export function sortIncidents(
  incidents: MatchReviewIncident[],
): MatchReviewIncident[] {
  return [...incidents].sort((a, b) => {
    if (a.round_number !== b.round_number) {
      return a.round_number - b.round_number;
    }
    if (a.anchor_demo_tick !== b.anchor_demo_tick) {
      return a.anchor_demo_tick - b.anchor_demo_tick;
    }
    if (a.rule_id !== b.rule_id) {
      return a.rule_id.localeCompare(b.rule_id);
    }
    return a.incident_id.localeCompare(b.incident_id);
  });
}

/** Timeline order: demo_tick → event_id (non-semantic within a tick). */
export function sortTimelineEvents(
  events: MatchReviewTimelineEvent[],
): MatchReviewTimelineEvent[] {
  return [...events].sort((a, b) => {
    if (a.demo_tick !== b.demo_tick) {
      return a.demo_tick - b.demo_tick;
    }
    return a.event_id.localeCompare(b.event_id);
  });
}

export function filterIncidents(
  incidents: MatchReviewIncident[],
  filters: ReviewFilters,
): MatchReviewIncident[] {
  return sortIncidents(incidents).filter((incident) => {
    if (filters.roundId !== "all" && incident.round_id !== filters.roundId) {
      return false;
    }
    if (
      filters.playerIdentityId !== "all" &&
      incident.focus_player_id !== filters.playerIdentityId
    ) {
      return false;
    }
    if (filters.ruleId !== "all" && incident.rule_id !== filters.ruleId) {
      return false;
    }
    if (filters.side !== "all" && incident.focus_side !== filters.side) {
      return false;
    }
    if (filters.severity !== "all" && incident.severity !== filters.severity) {
      return false;
    }
    return true;
  });
}

export function filterTimelineEvents(
  events: MatchReviewTimelineEvent[],
  filters: ReviewFilters,
): MatchReviewTimelineEvent[] {
  return sortTimelineEvents(events).filter((event) => {
    if (filters.roundId !== "all" && event.round_id !== filters.roundId) {
      return false;
    }
    if (
      filters.playerIdentityId !== "all" &&
      event.player_identity_id != null &&
      event.player_identity_id !== filters.playerIdentityId
    ) {
      return false;
    }
    if (filters.side !== "all" && event.side != null && event.side !== filters.side) {
      return false;
    }
    if (
      filters.ruleId !== "all" &&
      event.event_type === "incident_anchor" &&
      event.fields.rule_id !== filters.ruleId
    ) {
      return false;
    }
    return true;
  });
}

/** Group same-DemoTick events; within a group order by event_id only. */
export function groupTimelineByTick(
  events: MatchReviewTimelineEvent[],
): Array<{ demoTick: number; events: MatchReviewTimelineEvent[] }> {
  const sorted = sortTimelineEvents(events);
  const groups: Array<{ demoTick: number; events: MatchReviewTimelineEvent[] }> =
    [];
  for (const event of sorted) {
    const last = groups[groups.length - 1];
    if (last && last.demoTick === event.demo_tick) {
      last.events.push(event);
    } else {
      groups.push({ demoTick: event.demo_tick, events: [event] });
    }
  }
  return groups;
}

export function assertReviewShape(value: unknown): MatchReview {
  if (!value || typeof value !== "object") {
    throw new Error("MALFORMED_REVIEW: expected object");
  }
  const review = value as MatchReview;
  if (typeof review.schema_version !== "string") {
    throw new Error("MALFORMED_REVIEW: missing schema_version");
  }
  if (!review.match || typeof review.match.match_id !== "string") {
    throw new Error("MALFORMED_REVIEW: missing match.match_id");
  }
  if (!Array.isArray(review.rounds) || !Array.isArray(review.incidents)) {
    throw new Error("MALFORMED_REVIEW: rounds/incidents must be arrays");
  }
  if (!Array.isArray(review.unresolved_evaluations)) {
    throw new Error("MALFORMED_REVIEW: unresolved_evaluations must be an array");
  }
  return review;
}
