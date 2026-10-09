from __future__ import annotations

from pathlib import Path

from ..errors import ParserUnavailableError
from .models import ParsedDemo
from .ports import DemoParserAdapter


class CompositeDemoParser:
    """Prefer Awpy for high-level tables; demoparser2 fills gaps / denser kills."""

    name = "composite"

    def __init__(
        self,
        primary: DemoParserAdapter,
        fallback: DemoParserAdapter,
    ):
        self.primary = primary
        self.fallback = fallback

    def available(self) -> bool:
        return self.primary.available() or self.fallback.available()

    def version(self) -> str | None:
        versions: list[str] = []
        if self.primary.available() and self.primary.version():
            versions.append(str(self.primary.version()))
        if self.fallback.available() and self.fallback.version():
            versions.append(str(self.fallback.version()))
        return "+".join(versions) if versions else None

    def parse(self, demo_path: Path) -> ParsedDemo:
        path = Path(demo_path)
        primary_result = self.primary.parse(path) if self.primary.available() else None
        fallback_result = (
            self.fallback.parse(path) if self.fallback.available() else None
        )

        if primary_result is not None and fallback_result is not None:
            return _merge(primary_result, fallback_result)
        if primary_result is not None:
            return primary_result
        if fallback_result is not None:
            return fallback_result

        raise ParserUnavailableError(
            "No demo parser backend is available (awpy/demoparser2)."
        )


def _merge(primary: ParsedDemo, fallback: ParsedDemo) -> ParsedDemo:
    header = primary.header
    if header.map_name is None and fallback.header.map_name is not None:
        header = fallback.header

    kills = (
        fallback.kills if len(fallback.kills) > len(primary.kills) else primary.kills
    )
    damages = (
        fallback.damages
        if len(fallback.damages) > len(primary.damages)
        else primary.damages
    )

    grenades = (
        fallback.grenades
        if len(fallback.grenades) > len(primary.grenades)
        else primary.grenades
    )
    selected_ticks = primary.selected_ticks or fallback.selected_ticks
    event_counts = primary.event_counts or fallback.event_counts

    return ParsedDemo(
        parser_name=f"{primary.parser_name}+{fallback.parser_name}",
        parser_version=primary.parser_version or fallback.parser_version,
        normalization_schema_version=primary.normalization_schema_version,
        header=header,
        roster=primary.roster or fallback.roster,
        rounds=primary.rounds or fallback.rounds,
        kills=kills,
        damages=damages,
        grenades=grenades,
        selected_ticks=selected_ticks,
        event_counts=event_counts,
        source_path=primary.source_path or fallback.source_path,
    )
