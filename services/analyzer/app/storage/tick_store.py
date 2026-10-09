"""Port for high-volume tick datasets (Parquet/DuckDB later).

Dense player ticks must not be mirrored into SQLite.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Protocol, Sequence
import json

from ..demo.models import SelectedTickRow


class TickStore(Protocol):
    def write_ticks(
        self,
        match_id: str,
        rows: Sequence[SelectedTickRow],
        *,
        dataset: str = "selected",
    ) -> None: ...

    def query(
        self,
        match_id: str,
        *,
        dataset: str = "selected",
        player_id: str | None = None,
        tick_start: int | None = None,
        tick_end: int | None = None,
    ) -> list[SelectedTickRow]: ...

    def delete_match(self, match_id: str) -> None: ...


class NullTickStore:
    """No-op TickStore used when dense tick persistence is not configured."""

    def write_ticks(
        self,
        match_id: str,
        rows: Sequence[SelectedTickRow],
        *,
        dataset: str = "selected",
    ) -> None:
        return None

    def query(
        self,
        match_id: str,
        *,
        dataset: str = "selected",
        player_id: str | None = None,
        tick_start: int | None = None,
        tick_end: int | None = None,
    ) -> list[SelectedTickRow]:
        return []

    def delete_match(self, match_id: str) -> None:
        return None


class JsonTickStore:
    """Minimal filesystem TickStore for small selected-tick fixtures.

    Future Parquet/DuckDB backends should implement the same port. This store
    intentionally lives outside SQLite.
    """

    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, match_id: str, dataset: str) -> Path:
        return self.root / match_id / "ticks" / f"{dataset}.json"

    def write_ticks(
        self,
        match_id: str,
        rows: Sequence[SelectedTickRow],
        *,
        dataset: str = "selected",
    ) -> None:
        path = self._path(match_id, dataset)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(row) for row in rows]
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def query(
        self,
        match_id: str,
        *,
        dataset: str = "selected",
        player_id: str | None = None,
        tick_start: int | None = None,
        tick_end: int | None = None,
    ) -> list[SelectedTickRow]:
        path = self._path(match_id, dataset)
        if not path.exists():
            return []
        raw = json.loads(path.read_text(encoding="utf-8"))
        rows = [SelectedTickRow(**item) for item in raw]
        out: list[SelectedTickRow] = []
        for row in rows:
            if player_id is not None and row.player_id != player_id:
                continue
            if tick_start is not None and row.demo_tick < tick_start:
                continue
            if tick_end is not None and row.demo_tick > tick_end:
                continue
            out.append(row)
        return out

    def delete_match(self, match_id: str) -> None:
        match_dir = self.root / match_id
        if not match_dir.exists():
            return
        ticks_dir = match_dir / "ticks"
        if ticks_dir.exists():
            for child in ticks_dir.iterdir():
                child.unlink(missing_ok=True)
            ticks_dir.rmdir()
        if match_dir.exists() and not any(match_dir.iterdir()):
            match_dir.rmdir()
