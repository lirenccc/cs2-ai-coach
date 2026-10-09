"""Repositories for PlayerIdentity / ControllerSession / PawnLife."""

from __future__ import annotations

import sqlite3
import uuid

from ..domain.identity import ControllerSession, PawnLife, PlayerIdentity
from ..errors import AppError
from .db import Database


class IdentityRepository:
    def __init__(self, database: Database):
        self.database = database

    def upsert_player_identity(
        self,
        *,
        steamid64: str | None,
        display_name: str | None,
        identity_id: str | None = None,
    ) -> PlayerIdentity:
        with self.database.connect() as conn:
            if steamid64:
                row = conn.execute(
                    "SELECT id, steamid64, display_name_latest FROM player_identities WHERE steamid64 = ?",
                    (steamid64,),
                ).fetchone()
                if row:
                    conn.execute(
                        """
                        UPDATE player_identities
                        SET display_name_latest = COALESCE(?, display_name_latest),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (display_name, row["id"]),
                    )
                    conn.commit()
                    refreshed = conn.execute(
                        "SELECT id, steamid64, display_name_latest FROM player_identities WHERE id = ?",
                        (row["id"],),
                    ).fetchone()
                    return PlayerIdentity(**dict(refreshed))

            new_id = identity_id or str(uuid.uuid4())
            try:
                conn.execute(
                    """
                    INSERT INTO player_identities(id, steamid64, display_name_latest)
                    VALUES (?, ?, ?)
                    """,
                    (new_id, steamid64, display_name),
                )
            except sqlite3.IntegrityError as exc:
                raise AppError(
                    "STORAGE_IDENTITY_CONFLICT",
                    "Could not create player identity (duplicate or invalid reference).",
                    False,
                    {"steamid64": steamid64},
                ) from exc
            conn.commit()
            return PlayerIdentity(
                id=new_id,
                steamid64=steamid64,
                display_name_latest=display_name,
            )

    def get_player_identity(self, identity_id: str) -> PlayerIdentity | None:
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT id, steamid64, display_name_latest FROM player_identities WHERE id = ?",
                (identity_id,),
            ).fetchone()
        return PlayerIdentity(**dict(row)) if row else None

    def create_controller_session(self, session: ControllerSession) -> ControllerSession:
        with self.database.connect() as conn:
            if session.player_identity_id is not None:
                exists = conn.execute(
                    "SELECT 1 FROM player_identities WHERE id = ?",
                    (session.player_identity_id,),
                ).fetchone()
                if exists is None:
                    raise AppError(
                        "STORAGE_INVALID_IDENTITY_REF",
                        "ControllerSession references unknown PlayerIdentity.",
                        False,
                        {"player_identity_id": session.player_identity_id},
                    )
            try:
                conn.execute(
                    """
                    INSERT INTO controller_sessions(
                        id, match_id, userid, player_identity_id,
                        connected_demo_tick, disconnected_demo_tick, is_bot, is_hltv
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session.id,
                        session.match_id,
                        session.userid,
                        session.player_identity_id,
                        session.connected_demo_tick,
                        session.disconnected_demo_tick,
                        1 if session.is_bot else 0,
                        1 if session.is_hltv else 0,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise AppError(
                    "STORAGE_INVALID_IDENTITY_REF",
                    "ControllerSession foreign key or constraint failed.",
                    False,
                    {"match_id": session.match_id, "userid": session.userid},
                ) from exc
            conn.commit()
        return session

    def list_controller_sessions(self, match_id: str) -> list[ControllerSession]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, match_id, userid, player_identity_id,
                       connected_demo_tick, disconnected_demo_tick, is_bot, is_hltv
                FROM controller_sessions
                WHERE match_id = ?
                ORDER BY userid ASC, connected_demo_tick ASC
                """,
                (match_id,),
            ).fetchall()
        return [
            ControllerSession(
                id=row["id"],
                match_id=row["match_id"],
                userid=row["userid"],
                player_identity_id=row["player_identity_id"],
                connected_demo_tick=row["connected_demo_tick"],
                disconnected_demo_tick=row["disconnected_demo_tick"],
                is_bot=bool(row["is_bot"]),
                is_hltv=bool(row["is_hltv"]),
            )
            for row in rows
        ]

    def create_pawn_life(self, life: PawnLife) -> PawnLife:
        with self.database.connect() as conn:
            if life.controller_session_id is not None:
                exists = conn.execute(
                    "SELECT 1 FROM controller_sessions WHERE id = ?",
                    (life.controller_session_id,),
                ).fetchone()
                if exists is None:
                    raise AppError(
                        "STORAGE_INVALID_IDENTITY_REF",
                        "PawnLife references unknown ControllerSession.",
                        False,
                        {"controller_session_id": life.controller_session_id},
                    )
            try:
                conn.execute(
                    """
                    INSERT INTO pawn_lives(
                        id, match_id, controller_session_id, pawn_handle,
                        spawn_demo_tick, death_demo_tick
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        life.id,
                        life.match_id,
                        life.controller_session_id,
                        life.pawn_handle,
                        life.spawn_demo_tick,
                        life.death_demo_tick,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise AppError(
                    "STORAGE_INVALID_IDENTITY_REF",
                    "PawnLife foreign key or constraint failed.",
                    False,
                    {"match_id": life.match_id, "pawn_handle": life.pawn_handle},
                ) from exc
            conn.commit()
        return life

    def list_pawn_lives(self, match_id: str) -> list[PawnLife]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, match_id, controller_session_id, pawn_handle,
                       spawn_demo_tick, death_demo_tick
                FROM pawn_lives
                WHERE match_id = ?
                ORDER BY spawn_demo_tick ASC, death_demo_tick ASC
                """,
                (match_id,),
            ).fetchall()
        return [PawnLife(**dict(row)) for row in rows]
