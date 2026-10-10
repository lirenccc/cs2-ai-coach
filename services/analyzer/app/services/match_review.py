"""Build the offline Match Review projection from authoritative analyzer data.

The renderer must never recompute tactical rules; this service is the single
source for review rounds, timeline events, incidents, and analysis coverage.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from ..demo.hydrate import parsed_demo_from_dict
from ..demo.models import ParsedDemo
from ..errors import AppError
from ..rules import default_rules, rule_context_from_parsed
from ..rules.models import (
    RULE_ENGINE_CONTRACT_VERSION,
    IncidentCandidate,
    RuleEvaluationResult,
    UnresolvedEvaluation,
)
from ..rules.thresholds import RULE_THRESHOLDS_VERSION
from ..storage.match_repository import MatchRecord, MatchRepository

MATCH_REVIEW_SCHEMA_VERSION = "1.0.0"

# Stable public reason codes for UI (map from rule-engine snake_case reasons).
_REASON_CODES: dict[str, str] = {
    "trade_attribution_unresolved_takeover": "TAKEOVER_ATTRIBUTION_UNRESOLVED",
    "opening_death_crosses_unresolved_takeover": "TAKEOVER_ATTRIBUTION_UNRESOLVED",
    "trade_kill_attribution_unresolved": "TAKEOVER_ATTRIBUTION_UNRESOLVED",
    "missing_authoritative_side": "MISSING_SIDE_PROVENANCE",
    "missing_authoritative_side_for_trade": "MISSING_SIDE_PROVENANCE",
    "missing_round_side_teammates": "MISSING_SIDE_PROVENANCE",
    "missing_victim_identity": "MISSING_IDENTITY_PROVENANCE",
    "alive_unresolved": "MISSING_ALIVE_PROVENANCE",
    "missing_authoritative_round_winner": "MISSING_ROUND_WINNER",
}


class MatchNotFoundError(AppError):
    def __init__(self, match_id: str):
        super().__init__(
            "MATCH_NOT_FOUND",
            f"No match found for id {match_id}",
            False,
            {"match_id": match_id},
        )


class MatchNotParsedError(AppError):
    def __init__(self, match_id: str, parse_status: str | None = None):
        super().__init__(
            "MATCH_NOT_PARSED",
            "Match has no completed parsed payload for review.",
            False,
            {"match_id": match_id, "parse_status": parse_status},
        )


@dataclass(frozen=True, slots=True)
class MatchReviewBundle:
    """Internal builder result before Pydantic serialization."""

    payload: dict[str, Any]


def sort_incidents(incidents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Canonical incident order: round → anchor tick → rule_id → incident_id."""

    return sorted(
        incidents,
        key=lambda item: (
            int(item.get("round_number") or 0),
            int(item.get("anchor_demo_tick") or 0),
            str(item.get("rule_id") or ""),
            str(item.get("incident_id") or ""),
        ),
    )


def sort_timeline_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Canonical timeline order: demo_tick → event_id (non-semantic within tick)."""

    return sorted(
        events,
        key=lambda item: (
            int(item.get("demo_tick") or 0),
            str(item.get("event_id") or ""),
        ),
    )


def sort_rounds(rounds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rounds, key=lambda item: int(item.get("round_number") or 0))


def unresolved_reason_code(reason: str) -> str:
    if reason in _REASON_CODES:
        return _REASON_CODES[reason]
    if "takeover" in reason:
        return "TAKEOVER_ATTRIBUTION_UNRESOLVED"
    if "side" in reason:
        return "MISSING_SIDE_PROVENANCE"
    if "alive" in reason:
        return "MISSING_ALIVE_PROVENANCE"
    return reason.upper()


def incident_to_review(candidate: IncidentCandidate) -> dict[str, Any]:
    return {
        "incident_id": candidate.id,
        "rule_id": candidate.rule_id,
        "rule_version": candidate.rule_version,
        "incident_type": candidate.incident_type,
        "round_id": candidate.round_id,
        "round_number": candidate.round_no,
        "focus_player_id": candidate.focus_player_id,
        "focus_side": candidate.focus_side,
        "start_demo_tick": candidate.start_demo_tick,
        "anchor_demo_tick": candidate.anchor_demo_tick,
        "end_demo_tick": candidate.end_demo_tick,
        "severity": candidate.severity,
        "confidence": candidate.confidence,
        "metrics": dict(candidate.metrics),
        "evidence": [item.to_dict() for item in candidate.evidence],
        "status": candidate.status,
        "thresholds_version": RULE_THRESHOLDS_VERSION,
        # Reserved for future Click-to-CS2 / AI panels (not used by this UI).
        "capture_hint": dict(candidate.capture_hint),
    }


def unresolved_to_review(item: UnresolvedEvaluation) -> dict[str, Any]:
    return {
        "rule_id": item.rule_id,
        "round_id": item.round_id,
        "round_number": item.round_no,
        "subject": item.subject,
        "reason": item.reason,
        "reason_code": unresolved_reason_code(item.reason),
        "certainty": item.certainty,
    }


def build_analysis_coverage(
    results: list[RuleEvaluationResult],
) -> list[dict[str, Any]]:
    coverage: list[dict[str, Any]] = []
    for result in results:
        reason_counts = Counter(
            unresolved_reason_code(item.reason) for item in result.unresolved
        )
        coverage.append(
            {
                "rule_id": result.rule_id,
                "rule_version": result.rule_version,
                "matched": len(result.candidates),
                "unresolved": len(result.unresolved),
                "outcome": result.outcome.value,
                "unresolved_reasons": [
                    {"reason_code": code, "count": count}
                    for code, count in sorted(reason_counts.items())
                ],
            }
        )
    return coverage


def build_rounds(parsed: ParsedDemo) -> list[dict[str, Any]]:
    rounds: list[dict[str, Any]] = []
    for row in parsed.rounds:
        round_id = f"r{row.round_number}"
        rounds.append(
            {
                "round_id": round_id,
                "round_number": row.round_number,
                "start_demo_tick": row.freeze_end_tick,
                "freeze_end_demo_tick": row.freeze_end_tick,
                "end_demo_tick": row.end_tick,
                "winner_side": row.winner,
                "round_end_reason": row.win_reason,
            }
        )
    return sort_rounds(rounds)


def build_players(parsed: ParsedDemo) -> list[dict[str, Any]]:
    players: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in parsed.roster:
        if row.is_hltv:
            continue
        identity = row.player_id
        if identity in seen:
            continue
        seen.add(identity)
        players.append(
            {
                "player_identity_id": identity,
                "display_name": row.display_name,
                "is_bot": bool(row.is_bot),
            }
        )
    return sorted(players, key=lambda item: item["player_identity_id"])


def build_timeline(
    parsed: ParsedDemo,
    *,
    incidents: list[dict[str, Any]],
    side_by_round_player: dict[tuple[int, str], str],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    for row in parsed.rounds:
        round_id = f"r{row.round_number}"
        if row.freeze_end_tick is not None:
            events.append(
                {
                    "event_id": f"tl_freeze_{round_id}_{row.freeze_end_tick}",
                    "event_type": "round_freeze_end",
                    "demo_tick": row.freeze_end_tick,
                    "round_id": round_id,
                    "round_number": row.round_number,
                    "player_identity_id": None,
                    "side": None,
                    "fields": {},
                }
            )
        if row.end_tick is not None:
            fields: dict[str, Any] = {}
            if row.winner:
                fields["winner_side"] = row.winner
            if row.win_reason:
                fields["round_end_reason"] = row.win_reason
            # Surface bomb outcome as a distinct timeline category when present.
            event_type = "round_end"
            reason = (row.win_reason or "").lower()
            if "plant" in reason:
                event_type = "bomb_planted"
            elif "defus" in reason:
                event_type = "bomb_defused"
            elif "explod" in reason or reason == "target_bombed":
                event_type = "bomb_exploded"
            events.append(
                {
                    "event_id": f"tl_end_{round_id}_{row.end_tick}",
                    "event_type": event_type,
                    "demo_tick": row.end_tick,
                    "round_id": round_id,
                    "round_number": row.round_number,
                    "player_identity_id": None,
                    "side": None,
                    "fields": fields,
                }
            )

    for kill in parsed.kills:
        if kill.round_number is None:
            continue
        demo_tick = kill.demo_tick if kill.demo_tick is not None else kill.tick
        round_id = f"r{kill.round_number}"
        victim_side = side_by_round_player.get((kill.round_number, kill.victim_id))
        events.append(
            {
                "event_id": kill.event_id,
                "event_type": "player_death",
                "demo_tick": demo_tick,
                "round_id": round_id,
                "round_number": kill.round_number,
                "player_identity_id": kill.victim_id,
                "side": victim_side,
                "fields": {
                    "attacker_id": kill.attacker_id,
                    "weapon": kill.weapon,
                    "headshot": kill.headshot,
                },
            }
        )

    for incident in incidents:
        events.append(
            {
                "event_id": f"tl_inc_{incident['incident_id']}",
                "event_type": "incident_anchor",
                "demo_tick": int(incident["anchor_demo_tick"]),
                "round_id": incident["round_id"],
                "round_number": int(incident["round_number"]),
                "player_identity_id": incident.get("focus_player_id"),
                "side": incident.get("focus_side"),
                "fields": {
                    "incident_id": incident["incident_id"],
                    "rule_id": incident["rule_id"],
                    "incident_type": incident["incident_type"],
                    "start_demo_tick": incident["start_demo_tick"],
                    "end_demo_tick": incident["end_demo_tick"],
                },
            }
        )

    return sort_timeline_events(events)


def build_match_review_from_parsed(
    *,
    match: MatchRecord,
    parsed: ParsedDemo,
) -> dict[str, Any]:
    context = rule_context_from_parsed(parsed, match_id=match.id)
    results = [rule.evaluate(context) for rule in default_rules()]

    incidents = sort_incidents(
        [
            incident_to_review(candidate)
            for result in results
            for candidate in result.candidates
        ]
    )
    unresolved = [
        unresolved_to_review(item)
        for result in results
        for item in result.unresolved
    ]
    unresolved.sort(
        key=lambda item: (
            int(item["round_number"]),
            str(item["rule_id"]),
            str(item["subject"]),
            str(item["reason_code"]),
        )
    )

    side_by_round_player = {
        (state.round_id, state.player_identity_id): state.side
        for state in context.round_player_states
    }

    rounds = build_rounds(parsed)
    timeline = build_timeline(
        parsed,
        incidents=incidents,
        side_by_round_player=side_by_round_player,
    )

    return {
        "schema_version": MATCH_REVIEW_SCHEMA_VERSION,
        "rule_engine_contract_version": RULE_ENGINE_CONTRACT_VERSION,
        "thresholds_version": RULE_THRESHOLDS_VERSION,
        "match": {
            "match_id": match.id,
            "map_name": match.map_name or parsed.header.map_name,
            "parse_status": match.parse_status,
            "tick_rate": parsed.header.tick_rate,
            "parser_name": match.parser_name or parsed.parser_name,
            "parser_version": match.parser_version or parsed.parser_version,
            "round_count": match.round_count or len(parsed.rounds),
            "kill_count": match.kill_count or len(parsed.kills),
            "roster_count": match.roster_count or len(parsed.roster),
        },
        "players": build_players(parsed),
        "rounds": rounds,
        "timeline_events": timeline,
        "incidents": incidents,
        "analysis_coverage": build_analysis_coverage(results),
        "unresolved_evaluations": unresolved,
    }


class MatchReviewService:
    def __init__(self, match_repo: MatchRepository):
        self.match_repo = match_repo

    def get_review(self, match_id: str) -> dict[str, Any]:
        match = self.match_repo.get(match_id)
        if match is None:
            raise MatchNotFoundError(match_id)
        payload = self.match_repo.load_parsed_json(match_id)
        if payload is None:
            raise MatchNotParsedError(match_id, match.parse_status)
        parsed = parsed_demo_from_dict(payload)
        # Strip absolute path before any accidental leakage into derived fields.
        parsed = ParsedDemo(
            parser_name=parsed.parser_name,
            parser_version=parsed.parser_version,
            normalization_schema_version=parsed.normalization_schema_version,
            header=parsed.header,
            roster=parsed.roster,
            rounds=parsed.rounds,
            kills=parsed.kills,
            damages=parsed.damages,
            grenades=parsed.grenades,
            selected_ticks=parsed.selected_ticks,
            event_counts=parsed.event_counts,
            source_path=None,
        )
        review = build_match_review_from_parsed(match=match, parsed=parsed)
        # Privacy: never expose filesystem paths or tokens.
        assert "original_path" not in review["match"]
        assert "source_path" not in review["match"]
        assert "session_token" not in review
        return review
