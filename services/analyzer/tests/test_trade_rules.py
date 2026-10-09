from __future__ import annotations

import pytest

from app.rules.trades import Kill, is_opening_death, is_untraded_death


def test_opening_death():
    kills = [
        Kill(200, "enemy1", "focus"),
        Kill(300, "friend1", "enemy1"),
    ]
    assert is_opening_death(kills, "focus") is True
    assert is_opening_death(kills, "friend1") is False


def test_empty_round_has_no_opening_death():
    assert is_opening_death([], "focus") is False


def test_death_is_traded_inside_window():
    kills = [
        Kill(100, "enemy1", "focus"),
        Kill(120, "friend1", "enemy1"),
    ]
    assert is_untraded_death(kills, "focus", {"friend1"}, 20) is False


def test_trade_on_exact_boundary_counts():
    kills = [
        Kill(100, "enemy1", "focus"),
        Kill(120, "friend1", "enemy1"),
    ]
    assert is_untraded_death(kills, "focus", {"friend1"}, 20) is False


def test_late_trade_is_untraded_for_metric():
    kills = [
        Kill(100, "enemy1", "focus"),
        Kill(121, "friend1", "enemy1"),
    ]
    assert is_untraded_death(kills, "focus", {"friend1"}, 20) is True


def test_no_focus_death_returns_false():
    assert is_untraded_death([Kill(100, "a", "b")], "focus", {"friend1"}, 20) is False


def test_negative_trade_window_rejected():
    with pytest.raises(ValueError):
        is_untraded_death([], "focus", set(), -1)
