from __future__ import annotations

from typing import Any
import uuid


def stable_player_id(
    *,
    steamid: Any = None,
    name: Any = None,
    fallback: str | None = None,
) -> str:
    steam = _clean_steamid(steamid)
    if steam:
        return f"steam:{steam}"
    if fallback:
        return fallback
    if name is not None and str(name).strip():
        return f"name:{str(name).strip()}"
    return f"unknown:{uuid.uuid4()}"


def _clean_steamid(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"0", "nan", "None"}:
        return None
    # demoparser2 sometimes returns floats for steamids in DataFrames
    if text.endswith(".0") and text.replace(".", "", 1).isdigit():
        text = text[:-2]
    if text.isdigit() and text != "0":
        return text
    return text or None


def as_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y"}


def as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def new_event_id(prefix: str) -> str:
    return f"{prefix}:{uuid.uuid4()}"


def build_rounds_from_markers(
    freeze_end_ticks: list[int],
    officially_ended_ticks: list[int],
    win_panel_ticks: list[int],
) -> list[tuple[int, int | None, int | None]]:
    """Return (round_number, freeze_end_tick, end_tick) using the verified state machine."""
    freeze = sorted(freeze_end_ticks)
    ends = sorted(officially_ended_ticks)
    panels = sorted(win_panel_ticks)
    rows: list[tuple[int, int | None, int | None]] = []
    end_idx = 0
    for index, start in enumerate(freeze, start=1):
        end_tick: int | None = None
        while end_idx < len(ends) and ends[end_idx] < start:
            end_idx += 1
        if end_idx < len(ends):
            end_tick = ends[end_idx]
            end_idx += 1
        elif panels:
            # Final competitive round may only close via cs_win_panel_match.
            candidate = next((tick for tick in panels if tick >= start), None)
            end_tick = candidate
        rows.append((index, start, end_tick))
    return rows


def assign_round_number(tick: int, rounds: list[tuple[int, int | None, int | None]]) -> int | None:
    for number, freeze_end, end_tick in rounds:
        if freeze_end is None:
            continue
        if tick < freeze_end:
            continue
        if end_tick is None or tick <= end_tick:
            return number
    return None
