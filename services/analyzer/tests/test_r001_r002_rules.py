from __future__ import annotations

from app.domain.evidence import EvidenceCertainty
from app.rules import OpeningDeathRule, RuleOutcome, UntradedDeathRule
from rule_fixtures import ctx, death, five_v_five_sides, round_snap


def test_r001_opening_death_emits_for_first_victim():
    sides = five_v_five_sides()
    events = [
        death("k1", 200, "CT1", "T1", victim_side="ct", pawn_life_id="life_ct1"),
        death("k2", 250, "T1", "CT2", victim_side="t"),
    ]
    result = OpeningDeathRule().evaluate(
        ctx([round_snap(winner="t", sides=sides)], events)
    )
    assert result.outcome == RuleOutcome.MATCHED
    assert len(result.candidates) == 1
    assert result.candidates[0].focus_player_id == "CT1"
    assert result.candidates[0].focus_side == "ct"
    assert result.candidates[0].metrics["victim_pawn_life_id"] == "life_ct1"


def test_r001_same_tick_multi_opening_is_order_independent():
    sides = five_v_five_sides()
    events_a = [
        death("k1", 200, "CT1", "T1", victim_side="ct"),
        death("k2", 200, "CT2", "T2", victim_side="ct"),
    ]
    events_b = list(reversed(events_a))
    a = OpeningDeathRule().evaluate(ctx([round_snap(sides=sides)], events_a))
    b = OpeningDeathRule().evaluate(ctx([round_snap(sides=sides)], events_b))
    assert {c.focus_player_id for c in a.candidates} == {"CT1", "CT2"}
    assert {c.id for c in a.candidates} == {c.id for c in b.candidates}


def test_r001_halftime_uses_current_side_not_roster():
    pre = {"P1": "ct", "E1": "t"}
    post = {"P1": "t", "E1": "ct"}
    events = [
        death("a", 100, "P1", "E1", round_no=12, victim_side="ct"),
        death("b", 800, "P1", "E1", round_no=13, victim_side="t"),
    ]
    result = OpeningDeathRule().evaluate(
        ctx(
            [
                round_snap(round_no=12, sides=pre, freeze_end=50, end_tick=200),
                round_snap(round_no=13, sides=post, freeze_end=700, end_tick=900),
            ],
            events,
        )
    )
    by_round = {c.round_no: c for c in result.candidates}
    assert by_round[12].focus_side == "ct"
    assert by_round[13].focus_side == "t"


def test_r001_unresolved_takeover_does_not_emit():
    events = [
        death("k1", 200, "CT1", "T1", victim_side="ct", unresolved_takeover=True),
    ]
    result = OpeningDeathRule().evaluate(
        ctx([round_snap(sides=five_v_five_sides())], events)
    )
    assert result.candidates == ()
    assert result.outcome == RuleOutcome.UNRESOLVED


def test_r001_idempotent():
    events = [death("k1", 200, "CT1", "T1", victim_side="ct")]
    context = ctx([round_snap(sides=five_v_five_sides())], events)
    rule = OpeningDeathRule()
    assert rule.evaluate(context).to_dict() == rule.evaluate(context).to_dict()


def test_r002_untraded_when_no_trade():
    sides = five_v_five_sides()
    events = [
        death("k1", 100, "CT1", "T1", victim_side="ct"),
        death("k2", 150, "T2", "CT2", victim_side="t"),  # not the killer
    ]
    result = UntradedDeathRule().evaluate(
        ctx([round_snap(sides=sides)], events, trade_window_demo_ticks=20)
    )
    traded = [c for c in result.candidates if c.focus_player_id == "CT1"]
    assert len(traded) == 1


def test_r002_traded_inside_window_not_matched_for_focus():
    sides = five_v_five_sides()
    events = [
        death("k1", 100, "CT1", "T1", victim_side="ct"),
        death("k2", 110, "T1", "CT2", victim_side="t"),
    ]
    result = UntradedDeathRule().evaluate(
        ctx([round_snap(sides=sides)], events, trade_window_demo_ticks=20)
    )
    assert all(c.focus_player_id != "CT1" for c in result.candidates)


def test_r002_unresolved_takeover_not_false_untraded():
    sides = five_v_five_sides()
    events = [
        death(
            "k1",
            100,
            "CT1",
            "T1",
            victim_side="ct",
            unresolved_takeover=True,
        ),
    ]
    result = UntradedDeathRule().evaluate(
        ctx([round_snap(sides=sides)], events, trade_window_demo_ticks=20)
    )
    assert result.candidates == ()
    assert result.outcome == RuleOutcome.UNRESOLVED
    assert "unresolved" in result.unresolved[0].reason


def test_r002_unresolved_trade_kill_attribution():
    sides = five_v_five_sides()
    events = [
        death("k1", 100, "CT1", "T1", victim_side="ct"),
        death(
            "k2",
            110,
            "T1",
            "CT2",
            victim_side="t",
            unresolved_takeover=True,
        ),
    ]
    result = UntradedDeathRule().evaluate(
        ctx([round_snap(sides=sides)], events, trade_window_demo_ticks=20)
    )
    assert all(c.focus_player_id != "CT1" for c in result.candidates)
    assert any("trade_kill" in u.reason for u in result.unresolved)


def test_r002_missing_side_is_unresolved_not_false():
    events = [death("k1", 100, "CT1", "T1")]
    result = UntradedDeathRule().evaluate(
        ctx(
            [round_snap(sides={}, alive=set(), complete=False)],
            events,
            trade_window_demo_ticks=20,
        )
    )
    assert result.candidates == ()
    assert result.outcome == RuleOutcome.UNRESOLVED


def test_r002_certainty_unresolved_death():
    sides = five_v_five_sides()
    events = [
        death(
            "k1",
            100,
            "CT1",
            "T1",
            victim_side="ct",
            certainty=EvidenceCertainty.UNRESOLVED,
        ),
    ]
    result = UntradedDeathRule().evaluate(
        ctx([round_snap(sides=sides)], events, trade_window_demo_ticks=20)
    )
    assert result.candidates == ()
    assert result.outcome == RuleOutcome.UNRESOLVED
