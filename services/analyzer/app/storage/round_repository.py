"""Round and raw round-marker persistence."""

from __future__ import annotations

import sqlite3

from ..domain.match_events import RoundMarker, RoundRecord
from ..errors import AppError
from .db import Database


class RoundRepository:
    def __init__(self, database: Database):
        self.database = database

    def replace_rounds(
        self,
        match_id: str,
        rounds: list[RoundRecord],
        markers: list[RoundMarker],
    ) -> None:
        with self.database.connect() as conn:
            conn.execute("DELETE FROM round_markers WHERE match_id = ?", (match_id,))
            conn.execute("DELETE FROM rounds WHERE match_id = ?", (match_id,))
            for round_row in rounds:
                if round_row.match_id != match_id:
                    raise AppError(
                        "STORAGE_MATCH_MISMATCH",
                        "RoundRecord.match_id does not match target match.",
                        False,
                    )
                try:
                    conn.execute(
                        """
                        INSERT INTO rounds(
                            id, match_id, round_no, freeze_end_demo_tick,
                            end_demo_tick, end_marker_type, winner, win_reason
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            round_row.id,
                            round_row.match_id,
                            round_row.round_no,
                            round_row.freeze_end_demo_tick,
                            round_row.end_demo_tick,
                            round_row.end_marker_type,
                            round_row.winner,
                            round_row.win_reason,
                        ),
                    )
                except sqlite3.IntegrityError as exc:
                    raise AppError(
                        "STORAGE_ROUND_CONSTRAINT",
                        "Could not insert round row.",
                        False,
                        {"round_no": round_row.round_no},
                    ) from exc
            for marker in markers:
                if marker.match_id != match_id:
                    raise AppError(
                        "STORAGE_MATCH_MISMATCH",
                        "RoundMarker.match_id does not match target match.",
                        False,
                    )
                conn.execute(
                    """
                    INSERT INTO round_markers(
                        id, match_id, marker_type, demo_tick, server_tick, sequence_index
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        marker.id,
                        marker.match_id,
                        marker.marker_type,
                        marker.demo_tick,
                        marker.server_tick,
                        marker.sequence_index,
                    ),
                )
            conn.commit()

    def list_rounds(self, match_id: str) -> list[RoundRecord]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, match_id, round_no, freeze_end_demo_tick, end_demo_tick,
                       end_marker_type, winner, win_reason
                FROM rounds
                WHERE match_id = ?
                ORDER BY round_no ASC
                """,
                (match_id,),
            ).fetchall()
        return [RoundRecord(**dict(row)) for row in rows]

    def list_markers(self, match_id: str) -> list[RoundMarker]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, match_id, marker_type, demo_tick, server_tick, sequence_index
                FROM round_markers
                WHERE match_id = ?
                ORDER BY sequence_index ASC, demo_tick ASC
                """,
                (match_id,),
            ).fetchall()
        return [RoundMarker(**dict(row)) for row in rows]
