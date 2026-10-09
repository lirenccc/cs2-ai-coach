"""Redact PII from normalized parse results for golden fixtures."""

from __future__ import annotations

from typing import Any


def redact_parsed_demo(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a privacy-safe summary suitable for committing as golden JSON."""
    header = payload.get("header") or {}
    roster = payload.get("roster") or []
    event_counts = payload.get("event_counts") or {}
    kills = payload.get("kills") or []
    damages = payload.get("damages") or []
    grenades = payload.get("grenades") or []
    selected_ticks = payload.get("selected_ticks") or []
    rounds = payload.get("rounds") or []

    hltv = [row for row in roster if row.get("is_hltv")]
    humans = [
        row
        for row in roster
        if not row.get("is_hltv")
        and not row.get("is_bot")
        and _looks_like_steamid64(row.get("steamid64"))
    ]

    return {
        "normalization_schema_version": payload.get("normalization_schema_version"),
        "parser_name": payload.get("parser_name"),
        "parser_version": payload.get("parser_version"),
        "header": {
            "map_name": header.get("map_name"),
            "patch_version": header.get("patch_version"),
            "build_num": header.get("build_num"),
            "demo_version_name": header.get("demo_version_name"),
            "server_start_tick": header.get("server_start_tick"),
            "tick_rate": header.get("tick_rate"),
            "playback_ticks": header.get("playback_ticks"),
            "playback_time_seconds": header.get("playback_time_seconds"),
            "timing_source": (header.get("extras") or {}).get("timing_source"),
        },
        "roster": {
            "human_count": len(humans),
            "hltv_count": len(hltv),
            "teams": sorted(
                {row.get("team") for row in humans if row.get("team") is not None}
            ),
            "userid_present_count": sum(
                1 for row in roster if row.get("userid") is not None
            ),
        },
        "rounds": {
            "count": len(rounds),
            "freeze_end_ticks": [row.get("freeze_end_tick") for row in rounds],
        },
        "events": {
            "player_death": event_counts.get("player_death", len(kills)),
            "player_hurt": event_counts.get("player_hurt", len(damages)),
            "weapon_fire": event_counts.get("weapon_fire"),
            "round_freeze_end": event_counts.get("round_freeze_end"),
            "flashbang_detonate": event_counts.get("flashbang_detonate"),
            "hegrenade_detonate": event_counts.get("hegrenade_detonate"),
            "smokegrenade_detonate": event_counts.get("smokegrenade_detonate"),
            "inferno_startburn": event_counts.get("inferno_startburn"),
            "decoy_detonate": event_counts.get("decoy_detonate"),
            "grenade_total": len(grenades),
        },
        "kills": {
            "count": len(kills),
            "with_server_tick": sum(1 for row in kills if row.get("server_tick") is not None),
            "with_victim_userid": sum(
                1 for row in kills if row.get("victim_userid") is not None
            ),
            "with_victim_pawn": sum(
                1 for row in kills if row.get("victim_pawn") is not None
            ),
            "demo_ticks_sample": [row.get("demo_tick") for row in kills[:5]],
            "server_ticks_sample": [row.get("server_tick") for row in kills[:5]],
        },
        "damages": {
            "count": len(damages),
            "with_server_tick": sum(
                1 for row in damages if row.get("server_tick") is not None
            ),
        },
        "selected_ticks": {
            "count": len(selected_ticks),
            "unique_demo_ticks": len(
                {row.get("demo_tick") for row in selected_ticks}
            ),
            "selection_reasons": sorted(
                {
                    row.get("selection_reason")
                    for row in selected_ticks
                    if row.get("selection_reason")
                }
            ),
        },
    }


def _looks_like_steamid64(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    return text.isdigit() and len(text) >= 16 and text.startswith("7656")
