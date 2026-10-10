"""R002 Untraded Death — death without a teammate trade in the configured window."""

from __future__ import annotations

from .base import RuleMetadata
from .context import LifeEndingEvent, RuleContext, RoundSnapshot
from .ids import candidate_id, evidence_id
from .models import (
    EvidenceKind,
    IncidentCandidate,
    RuleEvaluationResult,
    RuleEvidence,
    UnresolvedEvaluation,
)
from .trades import Kill, is_untraded_death


RULE_ID = "R002"
RULE_VERSION = "1.0.0"
INCIDENT_TYPE = "UNTRADED_DEATH"


class UntradedDeathRule:
    """Deterministic untraded-death detector with P0.6A unresolved policy.

    Distinguishes:
    - condition definitely false → no candidate (NOT_MATCHED for that death)
    - insufficient authoritative evidence → UNRESOLVED (never invent ``false``)
    """

    @property
    def metadata(self) -> RuleMetadata:
        return RuleMetadata(
            id=RULE_ID,
            version=RULE_VERSION,
            incident_type=INCIDENT_TYPE,
            required_inputs=(
                "life_ending_events",
                "round_side_state",
                "trade_window_demo_ticks",
            ),
            default_thresholds={"trade_window_demo_ticks": 320},
        )

    def evaluate(self, context: RuleContext) -> RuleEvaluationResult:
        candidates: list[IncidentCandidate] = []
        unresolved: list[UnresolvedEvaluation] = []
        seen_ids: set[str] = set()
        window = context.thresholds.trade_window_demo_ticks

        for round_snap in context.rounds:
            events = context.events_for_round(round_snap.round_no)
            # Deduplicate by victim life: first death per identity in the round.
            first_death_by_victim: dict[str, LifeEndingEvent] = {}
            for event in sorted(events, key=lambda item: (item.demo_tick, item.event_id)):
                victim = event.victim_identity_id
                if not victim or victim in first_death_by_victim:
                    continue
                first_death_by_victim[victim] = event

            for victim, death in first_death_by_victim.items():
                outcome = self._evaluate_death(
                    context, round_snap, events, death, window
                )
                if isinstance(outcome, UnresolvedEvaluation):
                    unresolved.append(outcome)
                    continue
                if outcome is None:
                    continue
                if outcome.id in seen_ids:
                    continue
                seen_ids.add(outcome.id)
                candidates.append(outcome)

        candidates.sort(key=lambda item: (item.round_no, item.anchor_demo_tick, item.id))
        return RuleEvaluationResult(
            rule_id=RULE_ID,
            rule_version=RULE_VERSION,
            candidates=tuple(candidates),
            unresolved=tuple(unresolved),
        )

    def _evaluate_death(
        self,
        context: RuleContext,
        round_snap: RoundSnapshot,
        events: tuple[LifeEndingEvent, ...],
        death: LifeEndingEvent,
        window: int,
    ) -> IncidentCandidate | UnresolvedEvaluation | None:
        victim = death.victim_identity_id
        assert victim is not None

        if death.crosses_unresolved_takeover or death.certainty.value == "unresolved":
            return UnresolvedEvaluation(
                rule_id=RULE_ID,
                round_id=round_snap.round_id,
                round_no=round_snap.round_no,
                subject=victim,
                reason="trade_attribution_unresolved_takeover",
            )

        side = round_snap.player_sides.get(victim) or death.victim_side
        if side not in {"ct", "t"}:
            return UnresolvedEvaluation(
                rule_id=RULE_ID,
                round_id=round_snap.round_id,
                round_no=round_snap.round_no,
                subject=victim,
                reason="missing_authoritative_side_for_trade",
            )

        teammates = {
            identity
            for identity, player_side in round_snap.player_sides.items()
            if player_side == side and identity != victim
        }
        if not teammates and len(round_snap.player_sides) == 0:
            return UnresolvedEvaluation(
                rule_id=RULE_ID,
                round_id=round_snap.round_id,
                round_no=round_snap.round_no,
                subject=victim,
                reason="missing_round_side_teammates",
            )

        # Any potential trade kill in-window that itself crosses unresolved
        # takeover cannot be used to decide traded vs untraded.
        window_end = death.demo_tick + window
        for event in events:
            if not (death.demo_tick <= event.demo_tick <= window_end):
                continue
            if event.attacker_identity_id in teammates and event.victim_identity_id == (
                death.attacker_identity_id
            ):
                if event.crosses_unresolved_takeover or event.certainty.value == "unresolved":
                    return UnresolvedEvaluation(
                        rule_id=RULE_ID,
                        round_id=round_snap.round_id,
                        round_no=round_snap.round_no,
                        subject=victim,
                        reason="trade_kill_attribution_unresolved",
                    )

        kills = [
            Kill(
                tick=item.demo_tick,
                attacker_id=item.attacker_identity_id or "",
                victim_id=item.victim_identity_id or "",
            )
            for item in events
            if item.victim_identity_id
        ]
        if not is_untraded_death(kills, victim, teammates, window):
            return None

        end_tick = (
            round_snap.end_demo_tick
            if round_snap.end_demo_tick is not None
            else window_end
        )
        inc_id = candidate_id(
            rule_id=RULE_ID,
            rule_version=RULE_VERSION,
            match_id=context.match_id,
            round_id=round_snap.round_id,
            subject=victim,
            anchor_demo_tick=death.demo_tick,
        )
        evidence = (
            RuleEvidence(
                evidence_id=evidence_id(RULE_ID, death.event_id, "death"),
                kind=EvidenceKind.DEMO_EVENT,
                label="focus_death",
                demo_tick=death.demo_tick,
                ref=death.event_id,
                certainty=death.certainty.value,
            ),
            RuleEvidence(
                evidence_id=evidence_id(RULE_ID, round_snap.round_id, "trade_window"),
                kind=EvidenceKind.METRIC,
                label="trade_window",
                name="trade_window_demo_ticks",
                value=window,
                unit="demo_ticks",
            ),
            RuleEvidence(
                evidence_id=evidence_id(RULE_ID, round_snap.round_id, victim, "side"),
                kind=EvidenceKind.ROUND_STATE,
                label="victim_side",
                name="side",
                value=side,
                ref=round_snap.side_source,
                certainty="verified",
            ),
        )
        return IncidentCandidate(
            id=inc_id,
            rule_id=RULE_ID,
            rule_version=RULE_VERSION,
            incident_type=INCIDENT_TYPE,
            match_id=context.match_id,
            round_id=round_snap.round_id,
            round_no=round_snap.round_no,
            focus_player_id=victim,
            focus_side=side,
            start_demo_tick=death.demo_tick,
            anchor_demo_tick=death.demo_tick,
            end_demo_tick=end_tick,
            severity=3,
            confidence=1.0,
            metrics={
                "killer_identity_id": death.attacker_identity_id,
                "trade_window_demo_ticks": window,
                "teammate_ids": sorted(teammates),
                "victim_pawn_life_id": death.victim_pawn_life_id,
            },
            evidence=evidence,
            capture_hint={"preferred_demo_tick": death.demo_tick},
        )
