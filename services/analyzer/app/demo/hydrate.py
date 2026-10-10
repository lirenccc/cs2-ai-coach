"""Hydrate ParsedDemo from persisted JSON (Storage v2 parsed_json)."""

from __future__ import annotations

from typing import Any

from .models import (
    DamageRow,
    GrenadeRow,
    KillRow,
    MatchHeader,
    NORMALIZATION_SCHEMA_VERSION,
    ParsedDemo,
    PlayerRosterEntry,
    RoundRow,
    SelectedTickRow,
)


def parsed_demo_from_dict(payload: dict[str, Any]) -> ParsedDemo:
    """Rebuild a ParsedDemo from ``ParsedDemo.to_dict()`` / ``asdict`` JSON."""

    header_raw = payload.get("header") or {}
    header = MatchHeader(
        map_name=header_raw.get("map_name"),
        patch_version=header_raw.get("patch_version"),
        build_num=header_raw.get("build_num"),
        demo_version_name=header_raw.get("demo_version_name"),
        server_name=header_raw.get("server_name"),
        client_name=header_raw.get("client_name"),
        tick_rate=header_raw.get("tick_rate"),
        playback_ticks=header_raw.get("playback_ticks"),
        playback_time_seconds=header_raw.get("playback_time_seconds"),
        server_start_tick=header_raw.get("server_start_tick"),
        extras=dict(header_raw.get("extras") or {}),
    )

    roster = [
        PlayerRosterEntry(
            player_id=str(row["player_id"]),
            steamid64=row.get("steamid64"),
            display_name=row.get("display_name"),
            team=row.get("team"),
            is_bot=bool(row.get("is_bot", False)),
            is_hltv=bool(row.get("is_hltv", False)),
            userid=row.get("userid"),
            extras=dict(row.get("extras") or {}),
        )
        for row in payload.get("roster") or []
    ]

    rounds = [
        RoundRow(
            round_number=int(row["round_number"]),
            freeze_end_tick=row.get("freeze_end_tick"),
            end_tick=row.get("end_tick"),
            winner=row.get("winner"),
            win_reason=row.get("win_reason"),
            extras=dict(row.get("extras") or {}),
        )
        for row in payload.get("rounds") or []
    ]

    kills = [
        KillRow(
            event_id=str(row["event_id"]),
            tick=int(row["tick"]),
            attacker_id=row.get("attacker_id"),
            victim_id=str(row["victim_id"]),
            assister_id=row.get("assister_id"),
            weapon=row.get("weapon"),
            headshot=bool(row.get("headshot", False)),
            penetrated=bool(row.get("penetrated", False)),
            round_number=row.get("round_number"),
            demo_tick=row.get("demo_tick"),
            server_tick=row.get("server_tick"),
            victim_userid=row.get("victim_userid"),
            victim_pawn=row.get("victim_pawn"),
            attacker_userid=row.get("attacker_userid"),
            attacker_pawn=row.get("attacker_pawn"),
            assister_userid=row.get("assister_userid"),
            assister_pawn=row.get("assister_pawn"),
            extras=dict(row.get("extras") or {}),
        )
        for row in payload.get("kills") or []
    ]

    damages = [
        DamageRow(
            event_id=str(row["event_id"]),
            tick=int(row["tick"]),
            attacker_id=row.get("attacker_id"),
            victim_id=str(row["victim_id"]),
            hp_damage=int(row["hp_damage"]),
            armor_damage=int(row.get("armor_damage") or 0),
            weapon=row.get("weapon"),
            round_number=row.get("round_number"),
            demo_tick=row.get("demo_tick"),
            server_tick=row.get("server_tick"),
            victim_userid=row.get("victim_userid"),
            victim_pawn=row.get("victim_pawn"),
            attacker_userid=row.get("attacker_userid"),
            attacker_pawn=row.get("attacker_pawn"),
            extras=dict(row.get("extras") or {}),
        )
        for row in payload.get("damages") or []
    ]

    grenades = [
        GrenadeRow(
            event_id=str(row["event_id"]),
            tick=int(row["tick"]),
            grenade_type=str(row["grenade_type"]),
            thrower_id=row.get("thrower_id"),
            x=row.get("x"),
            y=row.get("y"),
            z=row.get("z"),
            round_number=row.get("round_number"),
            demo_tick=row.get("demo_tick"),
            server_tick=row.get("server_tick"),
            thrower_userid=row.get("thrower_userid"),
            extras=dict(row.get("extras") or {}),
        )
        for row in payload.get("grenades") or []
    ]

    selected_ticks = [
        SelectedTickRow(
            demo_tick=int(row["demo_tick"]),
            player_id=str(row["player_id"]),
            steamid64=row.get("steamid64"),
            x=row.get("x"),
            y=row.get("y"),
            z=row.get("z"),
            health=row.get("health"),
            team=row.get("team"),
            is_alive=row.get("is_alive"),
            selection_reason=str(row["selection_reason"]),
            extras=dict(row.get("extras") or {}),
        )
        for row in payload.get("selected_ticks") or []
    ]

    return ParsedDemo(
        parser_name=str(payload.get("parser_name") or "unknown"),
        parser_version=payload.get("parser_version"),
        normalization_schema_version=str(
            payload.get("normalization_schema_version") or NORMALIZATION_SCHEMA_VERSION
        ),
        header=header,
        roster=roster,
        rounds=rounds,
        kills=kills,
        damages=damages,
        grenades=grenades,
        selected_ticks=selected_ticks,
        event_counts=dict(payload.get("event_counts") or {}),
        # Never treat persisted absolute paths as review output; keep for internal
        # rule hydration only when present.
        source_path=payload.get("source_path"),
    )
