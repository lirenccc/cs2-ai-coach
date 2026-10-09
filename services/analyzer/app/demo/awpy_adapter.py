from __future__ import annotations

from importlib import metadata
from pathlib import Path
from typing import Any

from ..errors import (
    MissingExpectedEventError,
    ParserCrashError,
    ParserUnavailableError,
)
from .frames import frame_to_records
from .models import (
    NORMALIZATION_SCHEMA_VERSION,
    DamageRow,
    KillRow,
    MatchHeader,
    ParsedDemo,
    PlayerRosterEntry,
    RoundRow,
)
from .normalize import (
    as_bool,
    as_int,
    as_optional_str,
    assign_round_number,
    build_rounds_from_markers,
    new_event_id,
    stable_player_id,
)


class AwpyAdapter:
    """High-level Awpy 2.x adapter.

    Converts Polars/DataFrame outputs into `ParsedDemo` at the boundary.
    Missing sections stay empty so `CompositeDemoParser` can fill from
    demoparser2.
    """

    name = "awpy"

    def available(self) -> bool:
        try:
            import awpy  # noqa: F401
        except ImportError:
            return False
        return True

    def version(self) -> str | None:
        try:
            return metadata.version("awpy")
        except metadata.PackageNotFoundError:
            return None

    def parse(self, demo_path: Path) -> ParsedDemo:
        if not self.available():
            raise ParserUnavailableError("awpy is not installed.")

        path = Path(demo_path)
        try:
            from awpy import Demo

            # Do not invent a global tick rate; Awpy still requires an int default.
            # Event ticks come from the demo itself and remain authoritative.
            demo = Demo(path, verbose=False)
            demo.parse()
        except ParserUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ParserCrashError(
                "awpy failed while parsing the demo.",
                details={"cause": type(exc).__name__},
            ) from exc

        header_raw = _as_mapping(getattr(demo, "header", None))
        events = getattr(demo, "events", None)
        event_map = events if isinstance(events, dict) else {}

        kill_rows = _safe_frame_records(demo, "kills")
        damage_rows = _safe_frame_records(demo, "damages")
        roster = _roster_from_player_round_totals(
            _safe_frame_records(demo, "player_round_totals")
        )
        if not roster:
            roster = _roster_from_combat(kill_rows, damage_rows)

        freeze_ticks = [
            as_int(row.get("tick"))
            for row in frame_to_records(event_map.get("round_freeze_end"))
        ]
        # Prefer round_end (one per competitive round in Awpy 2) over
        # round_officially_ended which may include overtime markers.
        end_ticks = [
            as_int(row.get("tick"))
            for row in frame_to_records(event_map.get("round_end"))
        ]
        if not end_ticks:
            end_ticks = [
                as_int(row.get("tick"))
                for row in frame_to_records(event_map.get("round_officially_ended"))
            ]
        panel_ticks = [
            as_int(row.get("tick"))
            for row in frame_to_records(event_map.get("cs_win_panel_match"))
        ]
        round_specs = build_rounds_from_markers(freeze_ticks, end_ticks, panel_ticks)
        round_end_meta = {
            as_int(row.get("round") or row.get("round_num") or index): row
            for index, row in enumerate(
                frame_to_records(event_map.get("round_end")),
                start=1,
            )
        }
        rounds = [
            RoundRow(
                round_number=number,
                freeze_end_tick=freeze_end,
                end_tick=end_tick,
                winner=as_optional_str(
                    (round_end_meta.get(number) or {}).get("winner")
                ),
                win_reason=as_optional_str(
                    (round_end_meta.get(number) or {}).get("reason")
                ),
            )
            for number, freeze_end, end_tick in round_specs
        ]

        kills = [_normalize_kill_row(row, round_specs) for row in kill_rows]
        damages = [_normalize_damage_row(row, round_specs) for row in damage_rows]

        if path.stat().st_size > 1024 and not kills and not damages:
            raise MissingExpectedEventError(
                "awpy returned empty kill/damage tables for a non-trivial demo.",
                details={"size_bytes": path.stat().st_size},
            )

        header = MatchHeader(
            map_name=as_optional_str(
                header_raw.get("map_name")
                or header_raw.get("mapName")
            ),
            patch_version=as_optional_str(header_raw.get("patch_version")),
            build_num=as_optional_str(header_raw.get("build_num")),
            demo_version_name=as_optional_str(header_raw.get("demo_version_name")),
            server_name=as_optional_str(header_raw.get("server_name")),
            client_name=as_optional_str(header_raw.get("client_name")),
            extras={
                key: value
                for key, value in header_raw.items()
                if key
                not in {
                    "map_name",
                    "mapName",
                    "patch_version",
                    "build_num",
                    "demo_version_name",
                    "server_name",
                    "client_name",
                }
            },
        )

        return ParsedDemo(
            parser_name=self.name,
            parser_version=self.version(),
            normalization_schema_version=NORMALIZATION_SCHEMA_VERSION,
            header=header,
            roster=roster,
            rounds=rounds,
            kills=kills,
            damages=damages,
            source_path=str(path),
        )


def _safe_frame_records(demo: Any, attr: str) -> list[dict[str, Any]]:
    try:
        value = getattr(demo, attr)
    except Exception:  # noqa: BLE001 - Awpy properties may raise KeyError
        return []
    if value is None:
        return []
    try:
        return frame_to_records(value)
    except TypeError:
        return []


def _as_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "items"):
        return dict(value.items())
    return {}


def _roster_from_player_round_totals(rows: list[dict[str, Any]]) -> list[PlayerRosterEntry]:
    by_id: dict[str, PlayerRosterEntry] = {}
    for row in rows:
        steam = row.get("steamid") or row.get("steam_id") or row.get("steamid64")
        name = row.get("name") or row.get("player_name")
        player_id = stable_player_id(steamid=steam, name=name)
        side = as_optional_str(row.get("side") or row.get("team"))
        existing = by_id.get(player_id)
        if existing is None:
            by_id[player_id] = PlayerRosterEntry(
                player_id=player_id,
                steamid64=as_optional_str(steam),
                display_name=as_optional_str(name),
                team=side,
            )
        elif existing.team is None and side is not None:
            by_id[player_id] = PlayerRosterEntry(
                player_id=existing.player_id,
                steamid64=existing.steamid64,
                display_name=existing.display_name or as_optional_str(name),
                team=side,
                is_bot=existing.is_bot,
                is_hltv=existing.is_hltv,
            )
    return list(by_id.values())


def _roster_from_combat(
    kills: list[dict[str, Any]],
    damages: list[dict[str, Any]],
) -> list[PlayerRosterEntry]:
    by_id: dict[str, PlayerRosterEntry] = {}
    for row in [*kills, *damages]:
        for steam_key, name_key, side_key in (
            ("victim_steamid", "victim_name", "victim_side"),
            ("attacker_steamid", "attacker_name", "attacker_side"),
            ("user_steamid", "user_name", None),
        ):
            steam = row.get(steam_key)
            name = row.get(name_key)
            if steam is None and name is None:
                continue
            player_id = stable_player_id(steamid=steam, name=name)
            if player_id in by_id:
                continue
            by_id[player_id] = PlayerRosterEntry(
                player_id=player_id,
                steamid64=as_optional_str(steam),
                display_name=as_optional_str(name),
                team=as_optional_str(row.get(side_key)) if side_key else None,
            )
    return list(by_id.values())


def _normalize_kill_row(
    row: dict[str, Any],
    round_specs: list[tuple[int, int | None, int | None]],
) -> KillRow:
    tick = as_int(row.get("tick"))
    victim = stable_player_id(
        steamid=row.get("victim_steamid") or row.get("user_steamid"),
        name=row.get("victim_name") or row.get("user_name"),
    )
    attacker = None
    if row.get("attacker_steamid") or row.get("attacker_name"):
        attacker = stable_player_id(
            steamid=row.get("attacker_steamid"),
            name=row.get("attacker_name"),
        )
    assister = None
    if row.get("assister_steamid") or row.get("assister_name"):
        assister = stable_player_id(
            steamid=row.get("assister_steamid"),
            name=row.get("assister_name"),
        )
    round_number = _optional_int(row.get("round_num") or row.get("round"))
    if round_number is None:
        round_number = assign_round_number(tick, round_specs)
    return KillRow(
        event_id=new_event_id("kill"),
        tick=tick,
        attacker_id=attacker,
        victim_id=victim,
        assister_id=assister,
        weapon=as_optional_str(row.get("weapon")),
        headshot=as_bool(row.get("headshot")),
        penetrated=as_bool(row.get("penetrated")),
        round_number=round_number,
        extras={
            "source_parser": "awpy",
            "source_event": "kills",
            "demo_tick": tick,
            "attacker_side": as_optional_str(row.get("attacker_side")),
            "victim_side": as_optional_str(row.get("victim_side")),
        },
    )


def _normalize_damage_row(
    row: dict[str, Any],
    round_specs: list[tuple[int, int | None, int | None]],
) -> DamageRow:
    tick = as_int(row.get("tick"))
    victim = stable_player_id(
        steamid=row.get("victim_steamid") or row.get("user_steamid"),
        name=row.get("victim_name") or row.get("user_name"),
    )
    attacker = None
    if row.get("attacker_steamid") or row.get("attacker_name"):
        attacker = stable_player_id(
            steamid=row.get("attacker_steamid"),
            name=row.get("attacker_name"),
        )
    round_number = _optional_int(row.get("round_num") or row.get("round"))
    if round_number is None:
        round_number = assign_round_number(tick, round_specs)
    return DamageRow(
        event_id=new_event_id("damage"),
        tick=tick,
        attacker_id=attacker,
        victim_id=victim,
        hp_damage=as_int(row.get("hp_damage") or row.get("dmg_health")),
        armor_damage=as_int(row.get("armor_damage") or row.get("dmg_armor")),
        weapon=as_optional_str(row.get("weapon")),
        round_number=round_number,
        extras={
            "source_parser": "awpy",
            "source_event": "damages",
            "demo_tick": tick,
        },
    )


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
