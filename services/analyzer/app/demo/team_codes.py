"""Map CS2 entity team_num values to roster team codes.

These codes come from parser/entity state (player_info / tick props),
never from kill-side inference.
"""

from __future__ import annotations

from typing import Any


def team_code_from_num(value: Any) -> str | None:
    if value is None:
        return None
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        text = str(value).strip().upper()
        if text in {"T", "CT", "SPECTATOR", "SPEC"}:
            return "SPECTATOR" if text == "SPEC" else text
        return None
    if number == 2:
        return "T"
    if number == 3:
        return "CT"
    if number == 1:
        return "SPECTATOR"
    return None
