from __future__ import annotations

from importlib import metadata
from pathlib import Path
from typing import Any

from ..errors import (
    MissingExpectedEventError,
    ParserCompatibilityError,
    ParserCrashError,
    ParserUnavailableError,
)
from .frames import frame_to_records
from .models import (
    NORMALIZATION_SCHEMA_VERSION,
    DamageRow,
    GrenadeRow,
    KillRow,
    MatchHeader,
    ParsedDemo,
    PlayerRosterEntry,
    RoundRow,
    SelectedTickRow,
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
from .team_codes import team_code_from_num


# Event props demoparser2 exposes via player=/other=; userid/pawn are not
# available from demoparser2 0.42 and are filled from structural_probe.
_DEATH_PLAYER_PROPS = ["team_num", "health", "is_alive"]
_DEATH_OTHER = ["game_time", "total_rounds_played"]
_HURT_PLAYER_PROPS = ["team_num"]
_HURT_OTHER = ["game_time", "total_rounds_played"]

_GRENADE_EVENTS = (
    ("flashbang_detonate", "flashbang"),
    ("hegrenade_detonate", "hegrenade"),
    ("smokegrenade_detonate", "smokegrenade"),
    ("inferno_startburn", "inferno"),
    ("decoy_detonate", "decoy"),
)

_TICK_FIELDS = ["X", "Y", "Z", "health", "team_num", "is_alive"]


class Demoparser2Adapter:
    name = "demoparser2"

    def available(self) -> bool:
        try:
            import demoparser2  # noqa: F401
        except ImportError:
            return False
        return True

    def version(self) -> str | None:
        try:
            return metadata.version("demoparser2")
        except metadata.PackageNotFoundError:
            return None

    def _parser(self, demo_path: Path):
        if not self.available():
            raise ParserUnavailableError("demoparser2 is not installed.")
        from demoparser2 import DemoParser

        return DemoParser(str(demo_path))

    def parse(self, demo_path: Path) -> ParsedDemo:
        path = Path(demo_path)
        try:
            parser = self._parser(path)
            header_raw = dict(parser.parse_header() or {})
            roster_raw = frame_to_records(parser.parse_player_info())
            death_raw = frame_to_records(
                parser.parse_event(
                    "player_death",
                    player=_DEATH_PLAYER_PROPS,
                    other=_DEATH_OTHER,
                )
            )
            hurt_raw = frame_to_records(
                parser.parse_event(
                    "player_hurt",
                    player=_HURT_PLAYER_PROPS,
                    other=_HURT_OTHER,
                )
            )
            freeze_raw = frame_to_records(parser.parse_event("round_freeze_end"))
            ended_raw = frame_to_records(parser.parse_event("round_officially_ended"))
            panel_raw = frame_to_records(parser.parse_event("cs_win_panel_match"))
            weapon_fire_raw = frame_to_records(parser.parse_event("weapon_fire"))
            grenade_raw_by_type: dict[str, list[dict[str, Any]]] = {}
            for event_name, grenade_type in _GRENADE_EVENTS:
                grenade_raw_by_type[grenade_type] = frame_to_records(
                    parser.parse_event(event_name)
                )
        except ParserUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - translate any parser failure
            raise ParserCrashError(
                "demoparser2 failed while parsing the demo.",
                details={"cause": type(exc).__name__},
            ) from exc

        if path.stat().st_size > 1024 and not death_raw and not hurt_raw:
            raise MissingExpectedEventError(
                "demoparser2 returned empty kill/damage tables for a non-trivial demo.",
                details={"size_bytes": path.stat().st_size},
            )

        probe_summary, probe_events = _load_probe(path)
        probe_by_name = _index_probe_events(probe_events)

        round_specs = build_rounds_from_markers(
            [as_int(row.get("tick")) for row in freeze_raw],
            [as_int(row.get("tick")) for row in ended_raw],
            [as_int(row.get("tick")) for row in panel_raw],
        )
        rounds = [
            RoundRow(
                round_number=number,
                freeze_end_tick=freeze_end,
                end_tick=end_tick,
                extras={
                    "source_parser": "demoparser2",
                    "demo_tick_freeze_end": freeze_end,
                    "demo_tick_end": end_tick,
                },
            )
            for number, freeze_end, end_tick in round_specs
        ]

        roster = _normalize_roster(roster_raw, probe_summary)
        kills = [
            _normalize_kill_row(
                row,
                round_specs,
                probe_by_name.get("player_death", []),
                index,
            )
            for index, row in enumerate(death_raw)
        ]
        damages = [
            _normalize_damage_row(
                row,
                round_specs,
                probe_by_name.get("player_hurt", []),
                index,
            )
            for index, row in enumerate(hurt_raw)
        ]
        grenades: list[GrenadeRow] = []
        for grenade_type, rows in grenade_raw_by_type.items():
            probe_rows = probe_by_name.get(_grenade_event_name(grenade_type), [])
            for index, row in enumerate(rows):
                grenades.append(
                    _normalize_grenade_row(
                        row,
                        grenade_type,
                        round_specs,
                        probe_rows,
                        index,
                    )
                )

        freeze_ticks = sorted(
            {as_int(row.get("tick")) for row in freeze_raw if row.get("tick") is not None}
        )
        selected_ticks = _parse_selected_ticks(parser, freeze_ticks)

        header = _build_header(header_raw, probe_summary)
        if header.map_name is None:
            raise ParserCompatibilityError(
                "demoparser2 header did not include map_name.",
                details={"header_keys": sorted(header_raw.keys())},
            )

        event_counts = {
            "player_death": len(kills),
            "player_hurt": len(damages),
            "round_freeze_end": len(freeze_raw),
            "round_officially_ended": len(ended_raw),
            "cs_win_panel_match": len(panel_raw),
            "weapon_fire": len(weapon_fire_raw),
            "flashbang_detonate": len(grenade_raw_by_type.get("flashbang", [])),
            "hegrenade_detonate": len(grenade_raw_by_type.get("hegrenade", [])),
            "smokegrenade_detonate": len(grenade_raw_by_type.get("smokegrenade", [])),
            "inferno_startburn": len(grenade_raw_by_type.get("inferno", [])),
            "decoy_detonate": len(grenade_raw_by_type.get("decoy", [])),
        }

        return ParsedDemo(
            parser_name=self.name,
            parser_version=self.version(),
            normalization_schema_version=NORMALIZATION_SCHEMA_VERSION,
            header=header,
            roster=roster,
            rounds=rounds,
            kills=kills,
            damages=damages,
            grenades=grenades,
            selected_ticks=selected_ticks,
            event_counts=event_counts,
            source_path=str(path),
        )

    # Legacy helpers kept for older call sites / health probes.
    def parse_deaths(self, demo_path: Path) -> list[dict[str, Any]]:
        return [kill.__dict__ for kill in self.parse(demo_path).kills]

    def parse_ticks(self, demo_path: Path, fields: list[str]) -> list[dict[str, Any]]:
        parser = self._parser(demo_path)
        try:
            return frame_to_records(parser.parse_ticks(fields))
        except Exception as exc:  # noqa: BLE001
            raise ParserCrashError(
                "demoparser2 parse_ticks failed.",
                details={"cause": type(exc).__name__},
            ) from exc


def _load_probe(path: Path) -> tuple[Any | None, list[dict[str, Any]]]:
    """Structural probe supplies build_num, server_tick, userid/pawn, HLTV roster."""
    try:
        from .structural_probe import probe_demo

        return probe_demo(path, include_events=True)
    except Exception:  # noqa: BLE001 - optional enrichment; demoparser2 remains primary
        return None, []


def _index_probe_events(
    events: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    indexed: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        name = event.get("name")
        if not name:
            continue
        indexed.setdefault(str(name), []).append(event)
    return indexed


def _grenade_event_name(grenade_type: str) -> str:
    mapping = {
        "flashbang": "flashbang_detonate",
        "hegrenade": "hegrenade_detonate",
        "smokegrenade": "smokegrenade_detonate",
        "inferno": "inferno_startburn",
        "decoy": "decoy_detonate",
    }
    return mapping.get(grenade_type, grenade_type)


def _build_header(header_raw: dict[str, Any], probe_summary: Any | None) -> MatchHeader:
    probe_header = getattr(probe_summary, "header", None) or {}
    probe_playback = getattr(probe_summary, "playback", None) or {}

    build_num = as_optional_str(header_raw.get("build_num"))
    if build_num is None:
        build_num = as_optional_str(probe_header.get("build_num"))

    patch_version = as_optional_str(header_raw.get("patch_version"))
    if patch_version is None:
        patch_version = as_optional_str(probe_header.get("patch_version"))

    tick_rate = _as_optional_float(header_raw.get("tick_rate"))
    playback_ticks = _as_optional_int(header_raw.get("playback_ticks"))
    playback_time = _as_optional_float(header_raw.get("playback_time_seconds"))
    server_start_tick = _as_optional_int(header_raw.get("server_start_tick"))

    # demoparser2 header omits footer timing / build_num; use probe for this file only.
    if tick_rate is None:
        tick_rate = _as_optional_float(probe_playback.get("derived_tick_rate"))
    if playback_ticks is None:
        playback_ticks = _as_optional_int(probe_playback.get("playback_ticks"))
    if playback_time is None:
        playback_time = _as_optional_float(probe_playback.get("playback_time_seconds"))
    if server_start_tick is None:
        server_start_tick = _as_optional_int(probe_header.get("server_start_tick"))

    extras = {
        key: value
        for key, value in header_raw.items()
        if key
        not in {
            "map_name",
            "patch_version",
            "build_num",
            "demo_version_name",
            "server_name",
            "client_name",
            "tick_rate",
            "playback_ticks",
            "playback_time_seconds",
            "server_start_tick",
        }
    }
    if probe_summary is not None:
        extras["probe_sha256"] = getattr(probe_summary, "sha256", None)
        extras["timing_source"] = "structural_probe_file_info"
    else:
        extras["timing_source"] = "demoparser2_header_only"

    return MatchHeader(
        map_name=as_optional_str(header_raw.get("map_name") or probe_header.get("map_name")),
        patch_version=patch_version,
        build_num=build_num,
        demo_version_name=as_optional_str(
            header_raw.get("demo_version_name") or probe_header.get("demo_version_name")
        ),
        server_name=as_optional_str(header_raw.get("server_name")),
        client_name=as_optional_str(header_raw.get("client_name")),
        tick_rate=tick_rate,
        playback_ticks=playback_ticks,
        playback_time_seconds=playback_time,
        server_start_tick=server_start_tick,
        extras=extras,
    )


def _normalize_roster(
    roster_raw: list[dict[str, Any]],
    probe_summary: Any | None,
) -> list[PlayerRosterEntry]:
    probe_players = list(getattr(probe_summary, "roster", None) or [])
    probe_by_steam = {
        str(player.steamid64): player
        for player in probe_players
        if getattr(player, "steamid64", 0)
    }

    entries: list[PlayerRosterEntry] = []
    seen_steam: set[str] = set()

    for row in roster_raw:
        steam = _string_or_none(row.get("steamid") or row.get("steam_id") or row.get("steamid64"))
        name = row.get("name") or row.get("player_name") or row.get("user_name")
        player_id = stable_player_id(steamid=steam, name=name)
        probe_player = probe_by_steam.get(steam) if steam else None

        # Team comes from demoparser2 entity team_number, never kill inference.
        team = team_code_from_num(row.get("team_number") or row.get("team_num"))
        if team is None:
            team = as_optional_str(row.get("team_name") or row.get("team"))

        is_hltv = as_bool(row.get("is_hltv") or row.get("hltv"))
        is_bot = as_bool(row.get("is_bot") or row.get("fake_player"))
        userid = _as_optional_int(row.get("userid") or row.get("user_id"))
        if probe_player is not None:
            is_hltv = bool(probe_player.is_hltv) or is_hltv
            is_bot = bool(probe_player.fake_player) or is_bot
            if userid is None:
                userid = int(probe_player.userid)
        # demoparser2 sometimes emits non-Steam placeholders (e.g. "13").
        if steam and not _looks_like_steamid64(steam):
            is_bot = True

        if steam:
            seen_steam.add(steam)

        extras = {
            key: value
            for key, value in row.items()
            if key
            not in {
                "steamid",
                "steam_id",
                "steamid64",
                "name",
                "player_name",
                "user_name",
                "team_name",
                "team",
                "team_number",
                "team_num",
                "is_bot",
                "fake_player",
                "is_hltv",
                "hltv",
                "userid",
                "user_id",
            }
        }
        extras["team_source"] = "demoparser2_player_info"
        if steam and not _looks_like_steamid64(steam):
            extras["steamid_quality"] = "non_steam64_placeholder"

        entries.append(
            PlayerRosterEntry(
                player_id=player_id,
                steamid64=steam,
                display_name=as_optional_str(name),
                team=team,
                is_bot=is_bot,
                is_hltv=is_hltv,
                userid=userid,
                extras=extras,
            )
        )

    # demoparser2 player_info omits CSTV/HLTV; probe initial userinfo includes it.
    for probe_player in probe_players:
        if not probe_player.is_hltv:
            continue
        steam = str(probe_player.steamid64) if probe_player.steamid64 else None
        if steam and steam != "0" and steam in seen_steam:
            continue
        entries.append(
            PlayerRosterEntry(
                player_id=stable_player_id(
                    steamid=steam if steam and steam != "0" else None,
                    name=probe_player.name,
                    fallback="hltv:cstv",
                ),
                steamid64=None if not steam or steam == "0" else steam,
                display_name=as_optional_str(probe_player.name),
                team=None,
                is_bot=bool(probe_player.fake_player),
                is_hltv=True,
                userid=int(probe_player.userid),
                extras={
                    "team_source": "none",
                    "roster_source": "structural_probe_userinfo",
                },
            )
        )

    return entries


def _normalize_kill_row(
    row: dict[str, Any],
    round_specs: list[tuple[int, int | None, int | None]],
    probe_rows: list[dict[str, Any]],
    index: int,
) -> KillRow:
    tick = as_int(row.get("tick"))
    probe = probe_rows[index] if index < len(probe_rows) else {}
    values = probe.get("values") or {}
    server_tick = _as_optional_int(probe.get("server_tick"))

    victim = stable_player_id(
        steamid=row.get("user_steamid") or row.get("victim_steamid"),
        name=row.get("user_name") or row.get("victim_name"),
    )
    attacker = None
    if _string_or_none(row.get("attacker_steamid")) or row.get("attacker_name"):
        attacker = stable_player_id(
            steamid=row.get("attacker_steamid"),
            name=row.get("attacker_name"),
        )
    assister = None
    if _string_or_none(row.get("assister_steamid")) or row.get("assister_name"):
        assister = stable_player_id(
            steamid=row.get("assister_steamid"),
            name=row.get("assister_name"),
        )

    return KillRow(
        event_id=new_event_id("kill"),
        tick=tick,
        attacker_id=attacker,
        victim_id=victim,
        assister_id=assister,
        weapon=as_optional_str(row.get("weapon")),
        headshot=as_bool(row.get("headshot")),
        penetrated=as_bool(row.get("penetrated")),
        round_number=assign_round_number(tick, round_specs),
        demo_tick=tick,
        server_tick=server_tick,
        victim_userid=_userid_or_none(values.get("userid")),
        victim_pawn=_pawn_or_none(values.get("userid_pawn")),
        attacker_userid=_userid_or_none(values.get("attacker")),
        attacker_pawn=_pawn_or_none(values.get("attacker_pawn")),
        assister_userid=_userid_or_none(values.get("assister")),
        assister_pawn=_pawn_or_none(values.get("assister_pawn")),
        extras={
            "source_parser": "demoparser2",
            "source_event": "player_death",
            "game_time": row.get("game_time"),
            "total_rounds_played": row.get("total_rounds_played"),
            "victim_team": team_code_from_num(row.get("user_team_num")),
            "attacker_team": team_code_from_num(row.get("attacker_team_num")),
            "thrusmoke": as_bool(row.get("thrusmoke")),
            "attackerblind": as_bool(row.get("attackerblind")),
            "attackerinair": as_bool(row.get("attackerinair")),
            "distance": row.get("distance"),
            "hitgroup": row.get("hitgroup"),
            "userid_source": "structural_probe" if values else "unavailable",
        },
    )


def _normalize_damage_row(
    row: dict[str, Any],
    round_specs: list[tuple[int, int | None, int | None]],
    probe_rows: list[dict[str, Any]],
    index: int,
) -> DamageRow:
    tick = as_int(row.get("tick"))
    probe = probe_rows[index] if index < len(probe_rows) else {}
    values = probe.get("values") or {}

    victim = stable_player_id(
        steamid=row.get("user_steamid") or row.get("victim_steamid"),
        name=row.get("user_name") or row.get("victim_name"),
    )
    attacker = None
    if _string_or_none(row.get("attacker_steamid")) or row.get("attacker_name"):
        attacker = stable_player_id(
            steamid=row.get("attacker_steamid"),
            name=row.get("attacker_name"),
        )
    return DamageRow(
        event_id=new_event_id("damage"),
        tick=tick,
        attacker_id=attacker,
        victim_id=victim,
        hp_damage=as_int(row.get("dmg_health") or row.get("hp_damage")),
        armor_damage=as_int(row.get("dmg_armor") or row.get("armor_damage")),
        weapon=as_optional_str(row.get("weapon")),
        round_number=assign_round_number(tick, round_specs),
        demo_tick=tick,
        server_tick=_as_optional_int(probe.get("server_tick")),
        victim_userid=_userid_or_none(values.get("userid")),
        victim_pawn=_pawn_or_none(values.get("userid_pawn")),
        attacker_userid=_userid_or_none(values.get("attacker")),
        attacker_pawn=_pawn_or_none(values.get("attacker_pawn")),
        extras={
            "source_parser": "demoparser2",
            "source_event": "player_hurt",
            "game_time": row.get("game_time"),
            "victim_team": team_code_from_num(row.get("user_team_num")),
            "userid_source": "structural_probe" if values else "unavailable",
        },
    )


def _normalize_grenade_row(
    row: dict[str, Any],
    grenade_type: str,
    round_specs: list[tuple[int, int | None, int | None]],
    probe_rows: list[dict[str, Any]],
    index: int,
) -> GrenadeRow:
    tick = as_int(row.get("tick"))
    probe = probe_rows[index] if index < len(probe_rows) else {}
    values = probe.get("values") or {}
    thrower = None
    if _string_or_none(row.get("user_steamid")) or row.get("user_name"):
        thrower = stable_player_id(
            steamid=row.get("user_steamid"),
            name=row.get("user_name"),
        )
    return GrenadeRow(
        event_id=new_event_id("grenade"),
        tick=tick,
        grenade_type=grenade_type,
        thrower_id=thrower,
        x=_as_optional_float(row.get("x")),
        y=_as_optional_float(row.get("y")),
        z=_as_optional_float(row.get("z")),
        round_number=assign_round_number(tick, round_specs),
        demo_tick=tick,
        server_tick=_as_optional_int(probe.get("server_tick")),
        thrower_userid=_userid_or_none(values.get("userid")),
        extras={
            "source_parser": "demoparser2",
            "source_event": _grenade_event_name(grenade_type),
            "entityid": row.get("entityid"),
            "userid_source": "structural_probe" if values else "unavailable",
        },
    )


def _parse_selected_ticks(parser: Any, freeze_ticks: list[int]) -> list[SelectedTickRow]:
    if not freeze_ticks:
        return []
    try:
        frame = parser.parse_ticks(_TICK_FIELDS, ticks=freeze_ticks)
        rows = frame_to_records(frame)
    except Exception:  # noqa: BLE001 - selected ticks are best-effort enrichment
        return []

    selected: list[SelectedTickRow] = []
    for row in rows:
        steam = _string_or_none(row.get("steamid"))
        name = row.get("name")
        selected.append(
            SelectedTickRow(
                demo_tick=as_int(row.get("tick")),
                player_id=stable_player_id(steamid=steam, name=name),
                steamid64=steam,
                x=_as_optional_float(row.get("X") if "X" in row else row.get("x")),
                y=_as_optional_float(row.get("Y") if "Y" in row else row.get("y")),
                z=_as_optional_float(row.get("Z") if "Z" in row else row.get("z")),
                health=_as_optional_float(row.get("health")),
                team=team_code_from_num(row.get("team_num")),
                is_alive=as_bool(row.get("is_alive")) if row.get("is_alive") is not None else None,
                selection_reason="round_freeze_end",
                extras={"source_parser": "demoparser2"},
            )
        )
    return selected


def _userid_or_none(value: Any) -> int | None:
    userid = _as_optional_int(value)
    if userid is None:
        return None
    # CS2 sentinel for "no player"
    if userid in {0, 65535}:
        return None
    return userid


def _pawn_or_none(value: Any) -> int | None:
    pawn = _as_optional_int(value)
    if pawn is None or pawn == -1:
        return None
    return pawn


def _looks_like_steamid64(value: str) -> bool:
    return value.isdigit() and len(value) >= 16 and value.startswith("7656")


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"0", "0.0", "nan", "None"}:
        return None
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text


def _as_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None


def _as_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number
