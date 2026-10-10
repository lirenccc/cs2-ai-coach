"""R003 Advantage Loss Candidate — mechanical loss of a meaningful man-advantage.

Naming note
-----------
``docs/04_ANALYSIS_ENGINE.md`` historically numbered Isolated Contact as R003 and
Advantage Throw as R004. The first deterministic coaching batch adopts:

    R001 Opening Death
    R002 Untraded Death
    R003 Advantage Loss Candidate  (type: ADVANTAGE_LOSS_CANDIDATE)

Semantics are the conservative round-loss definition below — not the older
sketch that required a single high-risk death to explain the collapse.
"""

from __future__ import annotations

from .alive import advantage_for_side, reconstruct_alive_states
from .base import RuleMetadata
from .context import RuleContext, RoundSnapshot
from .ids import candidate_id, evidence_id
from .models import (
    EvidenceKind,
    IncidentCandidate,
    RuleEvaluationResult,
    RuleEvidence,
    UnresolvedEvaluation,
)


RULE_ID = "R003"
RULE_VERSION = "1.0.0"
INCIDENT_TYPE = "ADVANTAGE_LOSS_CANDIDATE"


def _severity_from_peak(peak_advantage: int) -> int:
    if peak_advantage >= 4:
        return 5
    if peak_advantage == 3:
        return 4
    if peak_advantage == 2:
        return 3
    return 2


class AdvantageLossRule:
    """Detect that a side reached a configured man-advantage and then lost the round.

    Does **not** assert blame, aim, utility, or positioning.
    """

    @property
    def metadata(self) -> RuleMetadata:
        return RuleMetadata(
            id=RULE_ID,
            version=RULE_VERSION,
            incident_type=INCIDENT_TYPE,
            required_inputs=(
                "round_side_state",
                "initial_alive",
                "life_ending_events",
                "authoritative_round_winner",
                "minimum_player_advantage",
            ),
            default_thresholds={"minimum_player_advantage": 2},
        )

    def evaluate(self, context: RuleContext) -> RuleEvaluationResult:
        threshold = context.thresholds.minimum_player_advantage
        candidates: list[IncidentCandidate] = []
        unresolved: list[UnresolvedEvaluation] = []
        seen_ids: set[str] = set()

        for round_snap in context.rounds:
            events = context.events_for_round(round_snap.round_no)
            round_results = self._evaluate_round(
                context, round_snap, events, threshold
            )
            for item in round_results:
                if isinstance(item, UnresolvedEvaluation):
                    unresolved.append(item)
                    continue
                if item.id in seen_ids:
                    continue
                seen_ids.add(item.id)
                candidates.append(item)

        candidates.sort(key=lambda item: (item.round_no, item.focus_side or "", item.id))
        return RuleEvaluationResult(
            rule_id=RULE_ID,
            rule_version=RULE_VERSION,
            candidates=tuple(candidates),
            unresolved=tuple(unresolved),
        )

    def _evaluate_round(
        self,
        context: RuleContext,
        round_snap: RoundSnapshot,
        events: tuple,
        threshold: int,
    ) -> list[IncidentCandidate | UnresolvedEvaluation]:
        winner = round_snap.winner
        if winner not in {"ct", "t"}:
            return [
                UnresolvedEvaluation(
                    rule_id=RULE_ID,
                    round_id=round_snap.round_id,
                    round_no=round_snap.round_no,
                    subject="round",
                    reason="missing_authoritative_round_winner",
                )
            ]

        reconstruction = reconstruct_alive_states(round_snap, events)
        if not reconstruction.ok:
            return [
                UnresolvedEvaluation(
                    rule_id=RULE_ID,
                    round_id=round_snap.round_id,
                    round_no=round_snap.round_no,
                    subject="alive_state",
                    reason=reconstruction.unresolved_reason or "alive_unresolved",
                )
            ]

        results: list[IncidentCandidate | UnresolvedEvaluation] = []
        for side in ("ct", "t"):
            candidate = self._candidate_for_side(
                context,
                round_snap,
                reconstruction.states,
                side=side,
                winner=winner,
                threshold=threshold,
            )
            if candidate is not None:
                results.append(candidate)
        return results

    def _candidate_for_side(
        self,
        context: RuleContext,
        round_snap: RoundSnapshot,
        states,
        *,
        side: str,
        winner: str,
        threshold: int,
    ) -> IncidentCandidate | None:
        peak_adv = -10**9
        peak_state = None
        min_later_adv: int | None = None
        collapse_tick: int | None = None

        for state in states:
            adv = advantage_for_side(state, side)
            if adv >= threshold and adv > peak_adv:
                peak_adv = adv
                peak_state = state

        if peak_state is None or peak_adv < threshold:
            return None

        # Conservative semantics: qualifying advantage AND that side lost the round.
        if winner == side:
            return None

        established = False
        for state in states:
            adv = advantage_for_side(state, side)
            if state.demo_tick < peak_state.demo_tick:
                continue
            if state.demo_tick == peak_state.demo_tick:
                established = True
                continue
            if not established:
                continue
            if min_later_adv is None or adv < min_later_adv:
                min_later_adv = adv
            if collapse_tick is None and adv < threshold:
                collapse_tick = state.demo_tick

        end_tick = (
            round_snap.end_demo_tick
            if round_snap.end_demo_tick is not None
            else states[-1].demo_tick
        )
        anchor = end_tick
        subject = f"side:{side}"
        inc_id = candidate_id(
            rule_id=RULE_ID,
            rule_version=RULE_VERSION,
            match_id=context.match_id,
            round_id=round_snap.round_id,
            subject=subject,
            anchor_demo_tick=anchor,
        )

        if side == "ct":
            peak_friendly, peak_enemy = peak_state.ct_alive, peak_state.t_alive
        else:
            peak_friendly, peak_enemy = peak_state.t_alive, peak_state.ct_alive

        evidence = (
            RuleEvidence(
                evidence_id=evidence_id(RULE_ID, round_snap.round_id, side, "peak"),
                kind=EvidenceKind.METRIC,
                label="qualifying_advantage_state",
                demo_tick=peak_state.demo_tick,
                name="peak_advantage",
                value={
                    "side": side,
                    "advantage": peak_adv,
                    "friendly_alive": peak_friendly,
                    "enemy_alive": peak_enemy,
                },
            ),
            RuleEvidence(
                evidence_id=evidence_id(RULE_ID, round_snap.round_id, "winner"),
                kind=EvidenceKind.ROUND_STATE,
                label="authoritative_round_outcome",
                demo_tick=end_tick,
                name="winner",
                value={
                    "winner": winner,
                    "win_reason": round_snap.win_reason,
                },
                certainty="verified",
            ),
            RuleEvidence(
                evidence_id=evidence_id(RULE_ID, round_snap.round_id, "side_src"),
                kind=EvidenceKind.ROUND_STATE,
                label="side_state_provenance",
                name="side_source",
                value=round_snap.side_source,
                certainty="verified",
            ),
        )
        if collapse_tick is not None:
            evidence = evidence + (
                RuleEvidence(
                    evidence_id=evidence_id(
                        RULE_ID, round_snap.round_id, side, "collapse"
                    ),
                    kind=EvidenceKind.METRIC,
                    label="advantage_collapse_below_threshold",
                    demo_tick=collapse_tick,
                    name="collapse_demo_tick",
                    value=collapse_tick,
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
            focus_player_id=None,
            focus_side=side,
            start_demo_tick=peak_state.demo_tick,
            anchor_demo_tick=anchor,
            end_demo_tick=end_tick,
            severity=_severity_from_peak(peak_adv),
            confidence=1.0,
            metrics={
                "peak_advantage": peak_adv,
                "peak_alive_friendly": peak_friendly,
                "peak_alive_enemy": peak_enemy,
                "peak_demo_tick": peak_state.demo_tick,
                "final_round_winner": winner,
                "win_reason": round_snap.win_reason,
                "collapse_demo_tick": collapse_tick,
                "minimum_later_advantage": min_later_adv,
                "minimum_player_advantage": threshold,
                "thresholds_version": context.thresholds.version,
            },
            evidence=evidence,
            capture_hint={
                "preferred_demo_tick": peak_state.demo_tick,
                "round_end_demo_tick": end_tick,
            },
        )
