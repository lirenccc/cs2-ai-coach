"""Map normalized ParsedDemo domain models into SQLite indexes + TickStore.

Parser-specific DataFrames must never reach this module.
"""

from __future__ import annotations

from collections import defaultdict
import uuid

from ..demo.models import ParsedDemo
from ..domain.identity import ControllerSession, PawnLife
from ..domain.match_events import (
    DamageEventRecord,
    GrenadeEventRecord,
    KillEventRecord,
    RoundMarker,
    RoundRecord,
)
from .event_repository import EventRepository
from .identity_repository import IdentityRepository
from .round_repository import RoundRepository
from .schema_versions import STRUCTURAL_PROBE_VERSION
from .tick_store import NullTickStore, TickStore


class PersistParsedDemoService:
    def __init__(
        self,
        identity_repository: IdentityRepository,
        round_repository: RoundRepository,
        event_repository: EventRepository,
        tick_store: TickStore | None = None,
    ):
        self.identity_repository = identity_repository
        self.round_repository = round_repository
        self.event_repository = event_repository
        self.tick_store: TickStore = tick_store or NullTickStore()

    def persist(self, match_id: str, parsed: ParsedDemo) -> None:
        sessions_by_userid = self._persist_identities(match_id, parsed)
        rounds_by_number = self._persist_rounds(match_id, parsed)
        self._persist_events(match_id, parsed, rounds_by_number, sessions_by_userid)
        if parsed.selected_ticks:
            self.tick_store.write_ticks(match_id, parsed.selected_ticks, dataset="selected")

    def _persist_identities(
        self,
        match_id: str,
        parsed: ParsedDemo,
    ) -> dict[int, str]:
        sessions_by_userid: dict[int, str] = {}
        for entry in parsed.roster:
            identity_id: str | None = None
            if entry.steamid64 and not entry.is_bot:
                identity = self.identity_repository.upsert_player_identity(
                    steamid64=entry.steamid64,
                    display_name=entry.display_name,
                )
                identity_id = identity.id
            elif entry.steamid64 and entry.is_bot:
                # Rare: bot with steam-like id — still keep optional identity.
                identity = self.identity_repository.upsert_player_identity(
                    steamid64=entry.steamid64,
                    display_name=entry.display_name,
                )
                identity_id = identity.id

            if entry.userid is None:
                continue
            session = ControllerSession(
                id=str(uuid.uuid4()),
                match_id=match_id,
                userid=entry.userid,
                player_identity_id=identity_id,
                connected_demo_tick=None,
                disconnected_demo_tick=None,
                is_bot=entry.is_bot,
                is_hltv=entry.is_hltv,
            )
            self.identity_repository.create_controller_session(session)
            sessions_by_userid[entry.userid] = session.id
        return sessions_by_userid

    def _persist_rounds(
        self,
        match_id: str,
        parsed: ParsedDemo,
    ) -> dict[int, str]:
        freeze_count = parsed.event_counts.get("round_freeze_end", len(parsed.rounds))
        official_count = parsed.event_counts.get("round_officially_ended", 0)
        use_final_fallback = freeze_count > official_count and bool(parsed.rounds)

        rounds: list[RoundRecord] = []
        markers: list[RoundMarker] = []
        rounds_by_number: dict[int, str] = {}
        freeze_seq = 0
        official_seq = 0
        panel_seq = 0

        for index, row in enumerate(parsed.rounds):
            is_last = index == len(parsed.rounds) - 1
            if row.end_tick is None:
                end_marker_type = None
            elif is_last and use_final_fallback:
                end_marker_type = "cs_win_panel_match"
            else:
                end_marker_type = "round_officially_ended"

            round_id = str(uuid.uuid4())
            rounds_by_number[row.round_number] = round_id
            rounds.append(
                RoundRecord(
                    id=round_id,
                    match_id=match_id,
                    round_no=row.round_number,
                    freeze_end_demo_tick=row.freeze_end_tick,
                    end_demo_tick=row.end_tick,
                    end_marker_type=end_marker_type,
                    winner=row.winner,
                    win_reason=row.win_reason,
                )
            )

            if row.freeze_end_tick is not None:
                freeze_seq += 1
                markers.append(
                    RoundMarker(
                        id=str(uuid.uuid4()),
                        match_id=match_id,
                        marker_type="round_freeze_end",
                        demo_tick=row.freeze_end_tick,
                        server_tick=None,
                        sequence_index=freeze_seq,
                    )
                )
            if row.end_tick is not None and end_marker_type == "round_officially_ended":
                official_seq += 1
                markers.append(
                    RoundMarker(
                        id=str(uuid.uuid4()),
                        match_id=match_id,
                        marker_type="round_officially_ended",
                        demo_tick=row.end_tick,
                        server_tick=None,
                        sequence_index=official_seq,
                    )
                )
            if row.end_tick is not None and end_marker_type == "cs_win_panel_match":
                panel_seq += 1
                markers.append(
                    RoundMarker(
                        id=str(uuid.uuid4()),
                        match_id=match_id,
                        marker_type="cs_win_panel_match",
                        demo_tick=row.end_tick,
                        server_tick=None,
                        sequence_index=panel_seq,
                    )
                )

        self.round_repository.replace_rounds(match_id, rounds, markers)
        return rounds_by_number

    def _persist_events(
        self,
        match_id: str,
        parsed: ParsedDemo,
        rounds_by_number: dict[int, str],
        sessions_by_userid: dict[int, str],
    ) -> None:
        pawn_lives_for_session: dict[str, list[int]] = defaultdict(list)
        kills: list[KillEventRecord] = []
        for kill in parsed.kills:
            demo_tick = kill.demo_tick if kill.demo_tick is not None else kill.tick
            round_id = (
                rounds_by_number.get(kill.round_number)
                if kill.round_number is not None
                else None
            )
            kills.append(
                KillEventRecord(
                    event_id=kill.event_id,
                    match_id=match_id,
                    round_id=round_id,
                    demo_tick=demo_tick,
                    server_tick=kill.server_tick,
                    victim_userid=kill.victim_userid,
                    victim_pawn_handle=kill.victim_pawn,
                    attacker_userid=kill.attacker_userid,
                    attacker_pawn_handle=kill.attacker_pawn,
                    assister_userid=kill.assister_userid,
                    assister_pawn_handle=kill.assister_pawn,
                    weapon=kill.weapon,
                    headshot=kill.headshot,
                    penetrated=kill.penetrated,
                    source_event_id=kill.event_id,
                    source_parser=parsed.parser_name,
                )
            )
            if kill.victim_userid is not None and kill.victim_pawn is not None:
                session_id = sessions_by_userid.get(kill.victim_userid)
                if session_id is not None:
                    if kill.victim_pawn not in pawn_lives_for_session[session_id]:
                        self.identity_repository.create_pawn_life(
                            PawnLife(
                                id=str(uuid.uuid4()),
                                match_id=match_id,
                                controller_session_id=session_id,
                                pawn_handle=kill.victim_pawn,
                                spawn_demo_tick=None,
                                death_demo_tick=demo_tick,
                            )
                        )
                        pawn_lives_for_session[session_id].append(kill.victim_pawn)

        damages = [
            DamageEventRecord(
                event_id=row.event_id,
                match_id=match_id,
                round_id=(
                    rounds_by_number.get(row.round_number)
                    if row.round_number is not None
                    else None
                ),
                demo_tick=row.demo_tick if row.demo_tick is not None else row.tick,
                server_tick=row.server_tick,
                victim_userid=row.victim_userid,
                victim_pawn_handle=row.victim_pawn,
                attacker_userid=row.attacker_userid,
                attacker_pawn_handle=row.attacker_pawn,
                hp_damage=row.hp_damage,
                armor_damage=row.armor_damage,
                weapon=row.weapon,
                source_event_id=row.event_id,
                source_parser=parsed.parser_name,
            )
            for row in parsed.damages
        ]
        grenades = [
            GrenadeEventRecord(
                event_id=row.event_id,
                match_id=match_id,
                round_id=(
                    rounds_by_number.get(row.round_number)
                    if row.round_number is not None
                    else None
                ),
                demo_tick=row.demo_tick if row.demo_tick is not None else row.tick,
                server_tick=row.server_tick,
                grenade_type=row.grenade_type,
                thrower_userid=row.thrower_userid,
                x=row.x,
                y=row.y,
                z=row.z,
                source_event_id=row.event_id,
                source_parser=parsed.parser_name,
            )
            for row in parsed.grenades
        ]
        self.event_repository.replace_combat_events(
            match_id,
            kills=kills,
            damages=damages,
            grenades=grenades,
        )


# Re-export for callers that only need the probe version constant nearby.
__all__ = ["PersistParsedDemoService", "STRUCTURAL_PROBE_VERSION"]
