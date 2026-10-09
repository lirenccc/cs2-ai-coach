from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .models import ParsedDemo


class DemoParserAdapter(Protocol):
    """Domain port for offline demo parsing.

    Implementations must return only normalized `ParsedDemo` values. Raw
    demoparser2 / awpy DataFrames stay inside the adapter.
    """

    @property
    def name(self) -> str: ...

    def available(self) -> bool: ...

    def version(self) -> str | None: ...

    def parse(self, demo_path: Path) -> ParsedDemo: ...


# Backward-compatible alias used by earlier scaffolding / docs.
DemoParserPort = DemoParserAdapter
