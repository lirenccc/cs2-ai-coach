from __future__ import annotations

import random

from app.domain.evidence import EvidenceCertainty
from app.rules import AdvantageLossRule, RuleOutcome
from app.rules.r003_advantage_loss import RULE_VERSION
from rule_fixtures import ctx, death, five_v_five_sides, round_snap


def _run(events, *, winner="t", sides=None, threshold=2, round_no=1, end=500):
    sides = sides or five_v_five_sides()
    context = ctx(
        [round_snap(round_no=round_no, winner=winner, sides=sides, end_tick=end)],
        events,
        minimum_player_advantage=threshold,
    )
    return AdvantageLossRule().evaluate(context)


def test_5v5_to_5v3_advantaged_team_loses_emits_candidate():
    # T get two kills → CT 5v3 advantage, then CT lose
    events = [
        death("k1", 200, "T1", "CT1", victim_side="t"),
        death("k2", 210, "T2", "CT2", victim_side="t"),
        death("k3", 300, "CT1", "T3", victim_side="ct"),
        death("k4", 310, "CT2", "T3", victim_side="ct"),
        death("k5", 320, "CT3", "T4", victim_side="ct"),
        death("k6", 330, "CT4", "T4", victim_side="ct"),
        death("k7", 340, "CT5", "T5", victim_side="ct"),
    ]
    result = _run(events, winner="t")
    assert result.outcome == RuleOutcome.MATCHED
    assert len(result.candidates) == 1
    cand = result.candidates[0]
    assert cand.incident_type == "ADVANTAGE_LOSS_CANDIDATE"
    assert cand.focus_side == "ct"
    assert cand.metrics["peak_advantage"] == 2
    assert cand.metrics["peak_alive_friendly"] == 5
    assert cand.metrics["peak_alive_enemy"] == 3
    assert cand.metrics["final_round_winner"] == "t"
    assert cand.start_demo_tick == 210
    assert cand.evidence


def test_5v5_to_5v4_below_threshold_no_candidate():
    events = [
        death("k1", 200, "T1", "CT1", victim_side="t"),
        death("k2", 300, "CT1", "T2", victim_side="ct"),
        death("k3", 310, "CT2", "T2", victim_side="ct"),
        death("k4", 320, "CT3", "T3", victim_side="ct"),
        death("k5", 330, "CT4", "T3", victim_side="ct"),
        death("k6", 340, "CT5", "T4", victim_side="ct"),
    ]
    result = _run(events, winner="t", threshold=2)
    assert result.candidates == ()
    assert result.outcome == RuleOutcome.NOT_MATCHED


def test_5v5_to_5v3_advantaged_team_wins_no_candidate():
    events = [
        death("k1", 200, "T1", "CT1", victim_side="t"),
        death("k2", 210, "T2", "CT1", victim_side="t"),
        death("k3", 300, "T3", "CT2", victim_side="t"),
        death("k4", 310, "T4", "CT2", victim_side="t"),
        death("k5", 320, "T5", "CT3", victim_side="t"),
    ]
    result = _run(events, winner="ct")
    assert result.candidates == ()
    assert result.outcome == RuleOutcome.NOT_MATCHED


def test_4v4_to_4v2_loss_emits_candidate():
    sides = {
        "CT1": "ct",
        "CT2": "ct",
        "CT3": "ct",
        "CT4": "ct",
        "T1": "t",
        "T2": "t",
        "T3": "t",
        "T4": "t",
    }
    events = [
        death("k1", 200, "T1", "CT1", victim_side="t"),
        death("k2", 210, "T2", "CT2", victim_side="t"),
        death("k3", 300, "CT1", "T3", victim_side="ct"),
        death("k4", 310, "CT2", "T3", victim_side="ct"),
        death("k5", 320, "CT3", "T4", victim_side="ct"),
        death("k6", 330, "CT4", "T4", victim_side="ct"),
    ]
    result = _run(events, winner="t", sides=sides)
    assert len(result.candidates) == 1
    assert result.candidates[0].metrics["peak_advantage"] == 2


def test_3v3_to_3v1_loss_emits_candidate():
    sides = {
        "CT1": "ct",
        "CT2": "ct",
        "CT3": "ct",
        "T1": "t",
        "T2": "t",
        "T3": "t",
    }
    events = [
        death("k1", 200, "T1", "CT1", victim_side="t"),
        death("k2", 210, "T2", "CT2", victim_side="t"),
        death("k3", 300, "CT1", "T3", victim_side="ct"),
        death("k4", 310, "CT2", "T3", victim_side="ct"),
        death("k5", 320, "CT3", "T3", victim_side="ct"),
    ]
    result = _run(events, winner="t", sides=sides)
    assert len(result.candidates) == 1
    assert result.candidates[0].metrics["peak_alive_friendly"] == 3
    assert result.candidates[0].metrics["peak_alive_enemy"] == 1


def test_halftime_pre_and_post_side_attribution():
    # Same identities, opposite sides across halftime.
    pre_sides = {"P1": "ct", "P2": "ct", "P3": "ct", "E1": "t", "E2": "t", "E3": "t"}
    post_sides = {"P1": "t", "P2": "t", "P3": "t", "E1": "ct", "E2": "ct", "E3": "ct"}

    pre_events = [
        death("a1", 200, "E1", "P1", round_no=12, victim_side="t"),
        death("a2", 210, "E2", "P2", round_no=12, victim_side="t"),
        death("a3", 300, "P1", "E3", round_no=12, victim_side="ct"),
        death("a4", 310, "P2", "E3", round_no=12, victim_side="ct"),
        death("a5", 320, "P3", "E3", round_no=12, victim_side="ct"),
    ]
    post_events = [
        death("b1", 800, "E1", "P1", round_no=13, victim_side="ct"),
        death("b2", 810, "E2", "P2", round_no=13, victim_side="ct"),
        death("b3", 900, "P1", "E3", round_no=13, victim_side="t"),
        death("b4", 910, "P2", "E3", round_no=13, victim_side="t"),
        death("b5", 920, "P3", "E3", round_no=13, victim_side="t"),
    ]
    context = ctx(
        [
            round_snap(
                round_no=12,
                winner="t",
                sides=pre_sides,
                freeze_end=100,
                end_tick=400,
            ),
            round_snap(
                round_no=13,
                winner="ct",
                sides=post_sides,
                freeze_end=700,
                end_tick=1000,
            ),
        ],
        pre_events + post_events,
    )
    result = AdvantageLossRule().evaluate(context)
    assert len(result.candidates) == 2
    by_round = {c.round_no: c for c in result.candidates}
    assert by_round[12].focus_side == "ct"
    assert by_round[13].focus_side == "t"


def test_same_tick_multi_kill_order_independent():
    base = [
        death("k1", 200, "T1", "CT1", victim_side="t"),
        death("k2", 200, "T2", "CT2", victim_side="t"),  # same tick → 5v3
        death("k3", 300, "CT1", "T3", victim_side="ct"),
        death("k4", 310, "CT2", "T3", victim_side="ct"),
        death("k5", 320, "CT3", "T4", victim_side="ct"),
        death("k6", 330, "CT4", "T4", victim_side="ct"),
        death("k7", 340, "CT5", "T5", victim_side="ct"),
    ]
    results = []
    for _ in range(8):
        shuffled = base[:]
        random.shuffle(shuffled)
        result = _run(shuffled, winner="t")
        assert len(result.candidates) == 1
        results.append(result.candidates[0].to_dict())
    assert all(item == results[0] for item in results)


def test_idempotent_repeated_evaluation():
    events = [
        death("k1", 200, "T1", "CT1", victim_side="t"),
        death("k2", 210, "T2", "CT2", victim_side="t"),
        death("k3", 400, "CT1", "T3", victim_side="ct"),
        death("k4", 410, "CT2", "T3", victim_side="ct"),
        death("k5", 420, "CT3", "T4", victim_side="ct"),
        death("k6", 430, "CT4", "T4", victim_side="ct"),
        death("k7", 440, "CT5", "T5", victim_side="ct"),
    ]
    context = ctx(
        [round_snap(winner="t", sides=five_v_five_sides())],
        events,
    )
    rule = AdvantageLossRule()
    first = rule.evaluate(context).to_dict()
    second = rule.evaluate(context).to_dict()
    assert first == second
    assert first["candidates"][0]["rule_version"] == RULE_VERSION


def test_duplicate_events_do_not_duplicate_candidates():
    events = [
        death("k1", 200, "T1", "CT1", victim_side="t"),
        death("k1", 200, "T1", "CT1", victim_side="t"),  # duplicate id/tick
        death("k2", 210, "T2", "CT2", victim_side="t"),
        death("k3", 300, "CT1", "T3", victim_side="ct"),
        death("k4", 310, "CT2", "T3", victim_side="ct"),
        death("k5", 320, "CT3", "T4", victim_side="ct"),
        death("k6", 330, "CT4", "T4", victim_side="ct"),
        death("k7", 340, "CT5", "T5", victim_side="ct"),
    ]
    result = _run(events, winner="t")
    assert len(result.candidates) == 1


def test_bot_takeover_authoritative_ownership_evaluates():
    events = [
        death(
            "k1",
            200,
            "T1",
            "CT1",
            victim_side="t",
            pawn_life_id="life_a",
        ),
        death(
            "k2",
            210,
            "T2",
            "CT2",
            victim_side="t",
            pawn_life_id="life_b",
        ),
        death("k3", 300, "CT1", "T3", victim_side="ct"),
        death("k4", 310, "CT2", "T3", victim_side="ct"),
        death("k5", 320, "CT3", "T4", victim_side="ct"),
        death("k6", 330, "CT4", "T4", victim_side="ct"),
        death("k7", 340, "CT5", "T5", victim_side="ct"),
    ]
    result = _run(events, winner="t")
    assert len(result.candidates) == 1


def test_unresolved_takeover_critical_ownership_no_confident_incident():
    events = [
        death("k1", 200, "T1", "CT1", victim_side="t"),
        death(
            "k2",
            210,
            "T2",
            "CT2",
            victim_side="t",
            unresolved_takeover=True,
        ),
        death("k3", 300, "CT1", "T3", victim_side="ct"),
    ]
    result = _run(events, winner="t")
    assert result.candidates == ()
    assert result.outcome == RuleOutcome.UNRESOLVED
    assert result.unresolved[0].reason.startswith("unresolved_takeover")


def test_authoritative_bomb_winner_not_guessed_from_last_kill():
    # CT have 5v3, last kill is CT dying, but authoritative winner is CT (bomb defuse
    # with survivors is possible — here we force win_reason/defuse + winner ct).
    events = [
        death("k1", 200, "T1", "CT1", victim_side="t"),
        death("k2", 210, "T2", "CT1", victim_side="t"),
        death("k3", 300, "CT5", "T3", victim_side="ct"),
    ]
    sides = five_v_five_sides()
    context = ctx(
        [
            round_snap(
                winner="ct",
                win_reason="bomb_defused",
                sides=sides,
            )
        ],
        events,
    )
    result = AdvantageLossRule().evaluate(context)
    # CT had advantage and won → no candidate; must not infer T win from last kill.
    assert result.candidates == ()


def test_time_expiration_winner_from_round_result():
    events = [
        death("k1", 200, "T1", "CT1", victim_side="t"),
        death("k2", 210, "T2", "CT2", victim_side="t"),
    ]
    context = ctx(
        [
            round_snap(
                winner="ct",
                win_reason="time_expired",
                sides=five_v_five_sides(),
            )
        ],
        events,
    )
    result = AdvantageLossRule().evaluate(context)
    assert result.candidates == ()


def test_suicide_changes_alive_state():
    events = [
        death("k1", 200, "T1", None, victim_side="t", suicide=True),
        death("k2", 210, "T2", None, victim_side="t", suicide=True),
        death("k3", 300, "CT1", "T3", victim_side="ct"),
        death("k4", 310, "CT2", "T3", victim_side="ct"),
        death("k5", 320, "CT3", "T4", victim_side="ct"),
        death("k6", 330, "CT4", "T4", victim_side="ct"),
        death("k7", 340, "CT5", "T5", victim_side="ct"),
    ]
    result = _run(events, winner="t")
    assert len(result.candidates) == 1
    assert result.candidates[0].metrics["peak_advantage"] == 2


def test_missing_side_provenance_is_unresolved():
    events = [death("k1", 200, "T1", "CT1", victim_side="t")]
    context = ctx(
        [
            round_snap(
                winner="t",
                sides={},
                alive=set(),
                complete=False,
            )
        ],
        events,
    )
    result = AdvantageLossRule().evaluate(context)
    assert result.candidates == ()
    assert result.outcome == RuleOutcome.UNRESOLVED


def test_missing_winner_is_unresolved():
    events = [
        death("k1", 200, "T1", "CT1", victim_side="t"),
        death("k2", 210, "T2", "CT2", victim_side="t"),
    ]
    context = ctx(
        [round_snap(winner=None, sides=five_v_five_sides())],
        events,
    )
    result = AdvantageLossRule().evaluate(context)
    assert result.outcome == RuleOutcome.UNRESOLVED
    assert "winner" in result.unresolved[0].reason


def test_unresolved_certainty_on_death_is_not_false_negative():
    events = [
        death(
            "k1",
            200,
            "T1",
            "CT1",
            victim_side="t",
            certainty=EvidenceCertainty.UNRESOLVED,
        ),
    ]
    result = _run(events, winner="t")
    assert result.candidates == ()
    assert result.outcome == RuleOutcome.UNRESOLVED


def test_death_absent_from_freeze_end_alive_set_is_ignored():
    """Parser gaps: identity not in freeze_end alive snapshot must not invent side."""

    sides = five_v_five_sides()
    alive = set(sides) - {"T5"}  # T5 absent from authoritative alive set
    events = [
        death("ghost", 150, "T5", "CT1", victim_side="t"),
        death("k1", 200, "T1", "CT1", victim_side="t"),
        death("k2", 210, "T2", "CT2", victim_side="t"),
        death("k3", 300, "CT1", "T3", victim_side="ct"),
        death("k4", 310, "CT2", "T3", victim_side="ct"),
        death("k5", 320, "CT3", "T4", victim_side="ct"),
        death("k6", 330, "CT4", "T4", victim_side="ct"),
        death("k7", 340, "CT5", "T3", victim_side="ct"),
    ]
    context = ctx(
        [round_snap(winner="t", sides=sides, alive=alive)],
        events,
    )
    result = AdvantageLossRule().evaluate(context)
    assert len(result.candidates) == 1
    assert result.unresolved == ()
