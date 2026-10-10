"""R001 Opening Death — first death in a round involving the focus identity."""

from __future__ import annotations

from .base import RuleMetadata
from .context import LifeEndingEvent, RuleContext
from .ids import candidate_id, evidence_id
from .models import (
    EvidenceKind,
    IncidentCandidate,
    RuleEvaluationResult,
    RuleEvidence,
    UnresolvedEvaluation,
)
from .trades import Kill, is_opening_death


RULE_ID = "R001"
RULE_VERSION = "1.0.0"
INCIDENT_TYPE = "OPENING_DEATH"


class OpeningDeathRule:
    """Deterministic opening-death detector.

    Preserves the ``is_opening_death`` primitive. Adds identity / side / evidence
    packaging required by the rule-engine contract.
    """

    @property
    def metadata(self) -> RuleMetadata:
        return RuleMetadata(
            id=RULE_ID,
            version=RULE_VERSION,
            incident_type=INCIDENT_TYPE,
            required_inputs=("life_ending_events", "round_side_state"),
            default_thresholds={},
        )

    def evaluate(self, context: RuleContext) -> RuleEvaluationResult:
        candidates: list[IncidentCandidate] = []
        unresolved: list[UnresolvedEvaluation] = []
        seen_ids: set[str] = set()

        for round_snap in context.rounds:
            events = context.events_for_round(round_snap.round_no)
            if not events:
                continue

            # Earliest DemoTick batch; within tick, stable by event_id.
            min_tick = min(event.demo_tick for event in events)
            opening_batch = sorted(
                (event for event in events if event.demo_tick == min_tick),
                key=lambda item: item.event_id,
            )
            # Same-tick multi-kill: all victims at the opening tick are opening deaths.
            for event in opening_batch:
                result = self._evaluate_event(context, round_snap.round_id, round_snap, event, events)
                if isinstance(result, UnresolvedEvaluation):
                    unresolved.append(result)
                    continue
                if result is None:
                    continue
                if result.id in seen_ids:
                    continue
                seen_ids.add(result.id)
                candidates.append(result)

        candidates.sort(key=lambda item: (item.round_no, item.anchor_demo_tick, item.id))
        return RuleEvaluationResult(
            rule_id=RULE_ID,
            rule_version=RULE_VERSION,
            candidates=tuple(candidates),
            unresolved=tuple(unresolved),
        )

    def _evaluate_event(
        self,
        context: RuleContext,
        round_id: str,
        round_snap,
        event: LifeEndingEvent,
        round_events: tuple[LifeEndingEvent, ...],
    ) -> IncidentCandidate | UnresolvedEvaluation | None:
        if event.crosses_unresolved_takeover:
            return UnresolvedEvaluation(
                rule_id=RULE_ID,
                round_id=round_id,
                round_no=round_snap.round_no,
                subject=event.event_id,
                reason="opening_death_crosses_unresolved_takeover",
            )
        if not event.victim_identity_id:
            return UnresolvedEvaluation(
                rule_id=RULE_ID,
                round_id=round_id,
                round_no=round_snap.round_no,
                subject=event.event_id,
                reason="missing_victim_identity",
            )

        victim = event.victim_identity_id
        side = round_snap.player_sides.get(victim) or event.victim_side
        if side not in {"ct", "t"}:
            return UnresolvedEvaluation(
                rule_id=RULE_ID,
                round_id=round_id,
                round_no=round_snap.round_no,
                subject=victim,
                reason="missing_authoritative_side",
            )

        kills = [
            Kill(
                tick=item.demo_tick,
                attacker_id=item.attacker_identity_id or "",
                victim_id=item.victim_identity_id or "",
            )
            for item in round_events
            if item.victim_identity_id
        ]
        if not is_opening_death(kills, victim):
            return None

        end_tick = round_snap.end_demo_tick if round_snap.end_demo_tick is not None else event.demo_tick
        teammates_alive = sorted(
            identity
            for identity, player_side in round_snap.player_sides.items()
            if player_side == side
            and identity != victim
            and identity in round_snap.initial_alive_identity_ids
        )
        # Adjust teammates for any same-tick co-deaths.
        co_deaths = {
            item.victim_identity_id
            for item in round_events
            if item.demo_tick == event.demo_tick and item.victim_identity_id
        }
        teammates_alive = [tid for tid in teammates_alive if tid not in co_deaths]

        inc_id = candidate_id(
            rule_id=RULE_ID,
            rule_version=RULE_VERSION,
            match_id=context.match_id,
            round_id=round_id,
            subject=victim,
            anchor_demo_tick=event.demo_tick,
        )
        evidence = (
            RuleEvidence(
                evidence_id=evidence_id(RULE_ID, event.event_id, "death"),
                kind=EvidenceKind.DEMO_EVENT,
                label="opening_death_event",
                demo_tick=event.demo_tick,
                ref=event.event_id,
                certainty=event.certainty.value,
            ),
            RuleEvidence(
                evidence_id=evidence_id(RULE_ID, round_id, victim, "side"),
                kind=EvidenceKind.ROUND_STATE,
                label="victim_side",
                name="side",
                value=side,
                certainty="verified",
                ref=round_snap.side_source,
            ),
            RuleEvidence(
                evidence_id=evidence_id(RULE_ID, round_id, victim, "teammates"),
                kind=EvidenceKind.METRIC,
                label="teammates_alive_at_opening",
                name="teammates_alive",
                value=len(teammates_alive),
                unit="players",
            ),
        )
        if event.victim_pawn_life_id:
            evidence = evidence + (
                RuleEvidence(
                    evidence_id=evidence_id(RULE_ID, event.victim_pawn_life_id),
                    kind=EvidenceKind.IDENTITY,
                    label="victim_pawn_life",
                    ref=event.victim_pawn_life_id,
                ),
            )

        return IncidentCandidate(
            id=inc_id,
            rule_id=RULE_ID,
            rule_version=RULE_VERSION,
            incident_type=INCIDENT_TYPE,
            match_id=context.match_id,
            round_id=round_id,
            round_no=round_snap.round_no,
            focus_player_id=victim,
            focus_side=side,
            start_demo_tick=event.demo_tick,
            anchor_demo_tick=event.demo_tick,
            end_demo_tick=end_tick,
            severity=2,
            confidence=1.0,
            metrics={
                "killer_identity_id": event.attacker_identity_id,
                "teammates_alive": teammates_alive,
                "victim_controller_session_id": event.victim_controller_session_id,
                "victim_pawn_life_id": event.victim_pawn_life_id,
            },
            evidence=evidence,
            capture_hint={"preferred_demo_tick": event.demo_tick},
        )
