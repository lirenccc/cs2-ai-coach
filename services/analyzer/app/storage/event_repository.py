"""Normalized kill/damage/grenade event indexes (not dense ticks)."""

from __future__ import annotations

import sqlite3

from ..domain.match_events import (
    DamageEventRecord,
    GrenadeEventRecord,
    KillEventRecord,
)
from ..errors import AppError
from .db import Database


class EventRepository:
    def __init__(self, database: Database):
        self.database = database

    def replace_combat_events(
        self,
        match_id: str,
        *,
        kills: list[KillEventRecord],
        damages: list[DamageEventRecord],
        grenades: list[GrenadeEventRecord],
    ) -> None:
        with self.database.connect() as conn:
            conn.execute("DELETE FROM kill_events WHERE match_id = ?", (match_id,))
            conn.execute("DELETE FROM damage_events WHERE match_id = ?", (match_id,))
            conn.execute("DELETE FROM grenade_events WHERE match_id = ?", (match_id,))
            for kill in kills:
                self._insert_kill(conn, match_id, kill)
            for damage in damages:
                self._insert_damage(conn, match_id, damage)
            for grenade in grenades:
                self._insert_grenade(conn, match_id, grenade)
            conn.commit()

    def insert_kill(self, kill: KillEventRecord) -> KillEventRecord:
        with self.database.connect() as conn:
            self._insert_kill(conn, kill.match_id, kill)
            conn.commit()
        return kill

    def list_kills(self, match_id: str) -> list[KillEventRecord]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT event_id, match_id, round_id, demo_tick, server_tick,
                       victim_userid, victim_pawn_handle, attacker_userid,
                       attacker_pawn_handle, assister_userid, assister_pawn_handle,
                       weapon, headshot, penetrated, source_event_id, source_parser
                FROM kill_events
                WHERE match_id = ?
                ORDER BY demo_tick ASC, event_id ASC
                """,
                (match_id,),
            ).fetchall()
        return [
            KillEventRecord(
                event_id=row["event_id"],
                match_id=row["match_id"],
                round_id=row["round_id"],
                demo_tick=row["demo_tick"],
                server_tick=row["server_tick"],
                victim_userid=row["victim_userid"],
                victim_pawn_handle=row["victim_pawn_handle"],
                attacker_userid=row["attacker_userid"],
                attacker_pawn_handle=row["attacker_pawn_handle"],
                assister_userid=row["assister_userid"],
                assister_pawn_handle=row["assister_pawn_handle"],
                weapon=row["weapon"],
                headshot=bool(row["headshot"]),
                penetrated=bool(row["penetrated"]),
                source_event_id=row["source_event_id"],
                source_parser=row["source_parser"],
            )
            for row in rows
        ]

    def list_damages(self, match_id: str) -> list[DamageEventRecord]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT event_id, match_id, round_id, demo_tick, server_tick,
                       victim_userid, victim_pawn_handle, attacker_userid,
                       attacker_pawn_handle, hp_damage, armor_damage, weapon,
                       source_event_id, source_parser
                FROM damage_events
                WHERE match_id = ?
                ORDER BY demo_tick ASC, event_id ASC
                """,
                (match_id,),
            ).fetchall()
        return [
            DamageEventRecord(
                event_id=row["event_id"],
                match_id=row["match_id"],
                round_id=row["round_id"],
                demo_tick=row["demo_tick"],
                server_tick=row["server_tick"],
                victim_userid=row["victim_userid"],
                victim_pawn_handle=row["victim_pawn_handle"],
                attacker_userid=row["attacker_userid"],
                attacker_pawn_handle=row["attacker_pawn_handle"],
                hp_damage=row["hp_damage"],
                armor_damage=row["armor_damage"],
                weapon=row["weapon"],
                source_event_id=row["source_event_id"],
                source_parser=row["source_parser"],
            )
            for row in rows
        ]

    def _insert_kill(
        self,
        conn: sqlite3.Connection,
        match_id: str,
        kill: KillEventRecord,
    ) -> None:
        if kill.match_id != match_id:
            raise AppError(
                "STORAGE_MATCH_MISMATCH",
                "KillEventRecord.match_id does not match target match.",
                False,
            )
        try:
            conn.execute(
                """
                INSERT INTO kill_events(
                    event_id, match_id, round_id, demo_tick, server_tick,
                    victim_userid, victim_pawn_handle, attacker_userid,
                    attacker_pawn_handle, assister_userid, assister_pawn_handle,
                    weapon, headshot, penetrated, source_event_id, source_parser
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    kill.event_id,
                    kill.match_id,
                    kill.round_id,
                    kill.demo_tick,
                    kill.server_tick,
                    kill.victim_userid,
                    kill.victim_pawn_handle,
                    kill.attacker_userid,
                    kill.attacker_pawn_handle,
                    kill.assister_userid,
                    kill.assister_pawn_handle,
                    kill.weapon,
                    1 if kill.headshot else 0,
                    1 if kill.penetrated else 0,
                    kill.source_event_id,
                    kill.source_parser,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise AppError(
                "STORAGE_INVALID_IDENTITY_REF",
                "Kill event foreign key or constraint failed.",
                False,
                {"event_id": kill.event_id, "round_id": kill.round_id},
            ) from exc

    def _insert_damage(
        self,
        conn: sqlite3.Connection,
        match_id: str,
        damage: DamageEventRecord,
    ) -> None:
        if damage.match_id != match_id:
            raise AppError(
                "STORAGE_MATCH_MISMATCH",
                "DamageEventRecord.match_id does not match target match.",
                False,
            )
        try:
            conn.execute(
                """
                INSERT INTO damage_events(
                    event_id, match_id, round_id, demo_tick, server_tick,
                    victim_userid, victim_pawn_handle, attacker_userid,
                    attacker_pawn_handle, hp_damage, armor_damage, weapon,
                    source_event_id, source_parser
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    damage.event_id,
                    damage.match_id,
                    damage.round_id,
                    damage.demo_tick,
                    damage.server_tick,
                    damage.victim_userid,
                    damage.victim_pawn_handle,
                    damage.attacker_userid,
                    damage.attacker_pawn_handle,
                    damage.hp_damage,
                    damage.armor_damage,
                    damage.weapon,
                    damage.source_event_id,
                    damage.source_parser,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise AppError(
                "STORAGE_INVALID_IDENTITY_REF",
                "Damage event foreign key or constraint failed.",
                False,
                {"event_id": damage.event_id},
            ) from exc

    def _insert_grenade(
        self,
        conn: sqlite3.Connection,
        match_id: str,
        grenade: GrenadeEventRecord,
    ) -> None:
        if grenade.match_id != match_id:
            raise AppError(
                "STORAGE_MATCH_MISMATCH",
                "GrenadeEventRecord.match_id does not match target match.",
                False,
            )
        try:
            conn.execute(
                """
                INSERT INTO grenade_events(
                    event_id, match_id, round_id, demo_tick, server_tick,
                    grenade_type, thrower_userid, x, y, z,
                    source_event_id, source_parser
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    grenade.event_id,
                    grenade.match_id,
                    grenade.round_id,
                    grenade.demo_tick,
                    grenade.server_tick,
                    grenade.grenade_type,
                    grenade.thrower_userid,
                    grenade.x,
                    grenade.y,
                    grenade.z,
                    grenade.source_event_id,
                    grenade.source_parser,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise AppError(
                "STORAGE_INVALID_IDENTITY_REF",
                "Grenade event foreign key or constraint failed.",
                False,
                {"event_id": grenade.event_id},
            ) from exc
