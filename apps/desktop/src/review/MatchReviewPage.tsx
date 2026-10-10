import { useMemo, useState } from "react";
import type {
  MatchReview,
  MatchReviewIncident,
} from "@cs2-ai-coach/contracts";
import {
  incidentTypeLabel,
  playerDisplayName,
  ruleLabel,
  sideLabel,
} from "./labels";
import {
  DEFAULT_REVIEW_FILTERS,
  filterIncidents,
  filterTimelineEvents,
  groupTimelineByTick,
  type ReviewFilters,
  type RoundFilter,
  type RuleFilter,
  type SeverityFilter,
  type SideFilter,
} from "./model";
import { formatDemoTick } from "./timing";

export interface MatchReviewPageProps {
  review: MatchReview;
  onBack: () => void;
}

export function MatchReviewPage({ review, onBack }: MatchReviewPageProps) {
  const [filters, setFilters] = useState<ReviewFilters>(DEFAULT_REVIEW_FILTERS);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const nameById = useMemo(() => {
    const map = new Map<string, string | null | undefined>();
    for (const player of review.players) {
      map.set(player.player_identity_id, player.display_name);
    }
    return map;
  }, [review.players]);

  const incidents = useMemo(
    () => filterIncidents(review.incidents, filters),
    [review.incidents, filters],
  );
  const timelineGroups = useMemo(
    () => groupTimelineByTick(filterTimelineEvents(review.timeline_events, filters)),
    [review.timeline_events, filters],
  );
  const selected = useMemo(
    () =>
      review.incidents.find((item) => item.incident_id === selectedId) ?? null,
    [review.incidents, selectedId],
  );
  const selectedRound = useMemo(() => {
    if (filters.roundId === "all") return null;
    return review.rounds.find((round) => round.round_id === filters.roundId) ?? null;
  }, [filters.roundId, review.rounds]);

  const tickRate = review.match.tick_rate;

  return (
    <section className="review" aria-label="Match review">
      <header className="reviewHeader">
        <div>
          <div className="eyebrow">MATCH REVIEW · OFFLINE</div>
          <h1>
            {review.match.map_name ?? "Unknown map"}{" "}
            <span className="mutedInline">#{review.match.match_id.slice(0, 8)}</span>
          </h1>
          <p>
            Deterministic R001–R003 projection · tick rate{" "}
            {tickRate != null && tickRate > 0 ? `${tickRate} Hz` : "unknown"} · no
            CS2 / AI required
          </p>
        </div>
        <button type="button" onClick={onBack}>
          返回
        </button>
      </header>

      <div className="reviewFilters" aria-label="Review filters">
        <label>
          Round
          <select
            aria-label="Filter by round"
            value={filters.roundId}
            onChange={(event) =>
              setFilters((prev) => ({
                ...prev,
                roundId: event.target.value as RoundFilter,
              }))
            }
          >
            <option value="all">All rounds</option>
            {review.rounds.map((round) => (
              <option key={round.round_id} value={round.round_id}>
                R{round.round_number}
              </option>
            ))}
          </select>
        </label>
        <label>
          Player
          <select
            aria-label="Filter by player"
            value={filters.playerIdentityId}
            onChange={(event) =>
              setFilters((prev) => ({
                ...prev,
                playerIdentityId: event.target.value,
              }))
            }
          >
            <option value="all">All players</option>
            {review.players.map((player) => (
              <option
                key={player.player_identity_id}
                value={player.player_identity_id}
              >
                {player.display_name || player.player_identity_id}
              </option>
            ))}
          </select>
        </label>
        <label>
          Rule
          <select
            aria-label="Filter by rule"
            value={filters.ruleId}
            onChange={(event) =>
              setFilters((prev) => ({
                ...prev,
                ruleId: event.target.value as RuleFilter,
              }))
            }
          >
            <option value="all">All rules</option>
            <option value="R001">{ruleLabel("R001")}</option>
            <option value="R002">{ruleLabel("R002")}</option>
            <option value="R003">{ruleLabel("R003")}</option>
          </select>
        </label>
        <label>
          Side
          <select
            aria-label="Filter by side"
            value={filters.side}
            onChange={(event) =>
              setFilters((prev) => ({
                ...prev,
                side: event.target.value as SideFilter,
              }))
            }
          >
            <option value="all">All sides</option>
            <option value="ct">CT</option>
            <option value="t">T</option>
          </select>
        </label>
        <label>
          Severity
          <select
            aria-label="Filter by severity"
            value={String(filters.severity)}
            onChange={(event) => {
              const raw = event.target.value;
              setFilters((prev) => ({
                ...prev,
                severity:
                  raw === "all" ? "all" : (Number(raw) as SeverityFilter),
              }));
            }}
          >
            <option value="all">All severities</option>
            {[1, 2, 3, 4, 5].map((level) => (
              <option key={level} value={level}>
                {level}
              </option>
            ))}
          </select>
        </label>
      </div>

      {selectedRound ? (
        <p className="reviewRoundMeta" aria-label="Selected round metadata">
          Round {selectedRound.round_number}: freeze{" "}
          {selectedRound.freeze_end_demo_tick ?? "—"} → end{" "}
          {selectedRound.end_demo_tick ?? "—"} · winner{" "}
          {sideLabel(selectedRound.winner_side)} ·{" "}
          {selectedRound.round_end_reason ?? "reason unknown"}
        </p>
      ) : null}

      <div className="reviewGrid">
        <aside className="reviewPanel" aria-label="Rounds">
          <h2>Rounds</h2>
          <ul className="reviewList">
            <li>
              <button
                type="button"
                className={filters.roundId === "all" ? "active" : undefined}
                onClick={() =>
                  setFilters((prev) => ({ ...prev, roundId: "all" }))
                }
              >
                All rounds
              </button>
            </li>
            {review.rounds.map((round) => (
              <li key={round.round_id}>
                <button
                  type="button"
                  className={
                    filters.roundId === round.round_id ? "active" : undefined
                  }
                  onClick={() =>
                    setFilters((prev) => ({
                      ...prev,
                      roundId: round.round_id,
                    }))
                  }
                >
                  R{round.round_number} · {sideLabel(round.winner_side)}
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <section className="reviewPanel" aria-label="Timeline">
          <h2>Timeline</h2>
          {timelineGroups.length === 0 ? (
            <p className="muted">No timeline events for current filters.</p>
          ) : (
            <ul className="timelineList">
              {timelineGroups.map((group) => (
                <li key={group.demoTick} className="timelineTickGroup">
                  <div className="timelineTick">
                    {formatDemoTick(group.demoTick, tickRate)}
                    {group.events.length > 1 ? (
                      <span className="sameTickBadge" title="Same DemoTick batch">
                        same tick ×{group.events.length}
                      </span>
                    ) : null}
                  </div>
                  <ul>
                    {group.events.map((event) => (
                      <li key={event.event_id}>
                        <span className="eventType">{event.event_type}</span>
                        {event.side ? ` · ${sideLabel(event.side)}` : ""}
                        {event.player_identity_id
                          ? ` · ${playerDisplayName(event.player_identity_id, nameById)}`
                          : ""}
                        {event.event_type === "incident_anchor" &&
                        typeof event.fields.rule_id === "string"
                          ? ` · ${ruleLabel(event.fields.rule_id)}`
                          : ""}
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="reviewPanel" aria-label="Incidents">
          <h2>Incidents</h2>
          {incidents.length === 0 ? (
            <p className="muted" role="status">
              No incidents for current filters. This is a valid analysis result.
            </p>
          ) : (
            <ul className="reviewList">
              {incidents.map((incident) => (
                <li key={incident.incident_id}>
                  <button
                    type="button"
                    className={
                      selectedId === incident.incident_id ? "active" : undefined
                    }
                    aria-label={`${ruleLabel(incident.rule_id)} round ${incident.round_number} severity ${incident.severity}`}
                    onClick={() => setSelectedId(incident.incident_id)}
                  >
                    <strong>
                      {incident.rule_id} · {incidentTypeLabel(incident.incident_type)}
                    </strong>
                    <span>
                      R{incident.round_number} · {sideLabel(incident.focus_side)} ·{" "}
                      {playerDisplayName(incident.focus_player_id, nameById)}
                    </span>
                    <span className="incidentMeta">
                      severity {incident.severity} · confidence{" "}
                      {incident.confidence.toFixed(2)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <section className="reviewPanel coverage" aria-label="Analysis coverage">
        <h2>Analysis coverage</h2>
        <p className="muted">
          UNRESOLVED evaluations are incomplete evidence — not coaching mistakes.
        </p>
        <ul className="coverageList">
          {review.analysis_coverage.map((row) => (
            <li key={row.rule_id}>
              <strong>
                {row.rule_id} · {ruleLabel(row.rule_id)}
              </strong>
              <span>
                matched {row.matched} · unresolved {row.unresolved}
              </span>
              {row.unresolved_reasons.length > 0 ? (
                <span className="mutedInline">
                  {row.unresolved_reasons
                    .map((item) => `${item.reason_code}×${item.count}`)
                    .join(", ")}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      </section>

      <EvidenceDrawer
        incident={selected}
        tickRate={tickRate}
        nameById={nameById}
        onClose={() => setSelectedId(null)}
      />
    </section>
  );
}

function EvidenceDrawer({
  incident,
  tickRate,
  nameById,
  onClose,
}: {
  incident: MatchReviewIncident | null;
  tickRate: number | null | undefined;
  nameById: Map<string, string | null | undefined>;
  onClose: () => void;
}) {
  if (!incident) {
    return (
      <section className="evidenceDrawer empty" aria-label="Incident evidence">
        <h2>Evidence</h2>
        <p className="muted">Select an incident to inspect structured evidence.</p>
        <p className="muted">
          Future: View in CS2 (anchor tick) · optional AI explanation panel.
        </p>
      </section>
    );
  }

  return (
    <section className="evidenceDrawer" aria-label="Incident evidence">
      <div className="cardTop">
        <h2>
          {incident.rule_id} · {incidentTypeLabel(incident.incident_type)}
        </h2>
        <button type="button" onClick={onClose}>
          Close
        </button>
      </div>
      <dl className="evidenceDl">
        <dt>Incident ID</dt>
        <dd>{incident.incident_id}</dd>
        <dt>Rule version</dt>
        <dd>{incident.rule_version}</dd>
        <dt>Thresholds</dt>
        <dd>{incident.thresholds_version ?? "—"}</dd>
        <dt>Round</dt>
        <dd>
          {incident.round_id} (R{incident.round_number})
        </dd>
        <dt>Subject</dt>
        <dd>
          {playerDisplayName(incident.focus_player_id, nameById)} ·{" "}
          {sideLabel(incident.focus_side)}
        </dd>
        <dt>Window</dt>
        <dd>
          {formatDemoTick(incident.start_demo_tick, tickRate)} →{" "}
          {formatDemoTick(incident.end_demo_tick, tickRate)}
        </dd>
        <dt>Anchor</dt>
        <dd>{formatDemoTick(incident.anchor_demo_tick, tickRate)}</dd>
        <dt>Severity</dt>
        <dd>{incident.severity}</dd>
        <dt>Confidence</dt>
        <dd>{incident.confidence.toFixed(2)}</dd>
      </dl>

      <h3>Metrics</h3>
      <ul className="metricList">
        {Object.keys(incident.metrics).length === 0 ? (
          <li className="muted">No metrics</li>
        ) : (
          Object.entries(incident.metrics).map(([key, value]) => (
            <li key={key}>
              <code>{key}</code>: {formatMetric(value)}
            </li>
          ))
        )}
      </ul>

      <h3>Evidence</h3>
      <ul className="evidenceItems">
        {incident.evidence.map((item) => (
          <li key={item.evidence_id}>
            <strong>{item.label}</strong>
            <span>
              {item.kind}
              {item.demo_tick != null
                ? ` · ${formatDemoTick(item.demo_tick, tickRate)}`
                : ""}
              {item.certainty ? ` · ${item.certainty}` : ""}
            </span>
            {item.name != null ? (
              <span>
                <code>{item.name}</code>
                {item.value != null ? `: ${formatMetric(item.value)}` : ""}
              </span>
            ) : null}
            <details>
              <summary>Details / IDs</summary>
              <code>{item.evidence_id}</code>
              {item.ref ? <div>ref: {item.ref}</div> : null}
            </details>
          </li>
        ))}
      </ul>
    </section>
  );
}

function formatMetric(value: unknown): string {
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}
