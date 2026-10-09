from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..demo.archive import ResolvedDemo, resolve_demo_file
from ..demo.files import looks_like_pbdems2, sha256_file
from ..demo.models import ParsedDemo
from ..demo.ports import DemoParserAdapter
from ..errors import AppError
from ..storage.demo_repository import DemoRecord, DemoRepository
from ..storage.match_repository import MatchRecord, MatchRepository


@dataclass(frozen=True, slots=True)
class ImportResult:
    record: DemoRecord
    match: MatchRecord
    deduplicated: bool
    resolved: ResolvedDemo
    parsed: ParsedDemo | None


class ImportDemoService:
    def __init__(
        self,
        demo_repository: DemoRepository,
        match_repository: MatchRepository,
        parser: DemoParserAdapter,
        *,
        extract_root: Path,
    ):
        self.demo_repository = demo_repository
        self.match_repository = match_repository
        self.parser = parser
        self.extract_root = Path(extract_root)

    def execute(self, raw_path: str) -> ImportResult:
        resolved = resolve_demo_file(raw_path, extract_root=self.extract_root)
        digest = sha256_file(resolved.demo_path)

        existing = self.demo_repository.find_by_sha256(digest)
        if existing:
            match = self.match_repository.find_by_demo_id(existing.id)
            if match is None:
                match = self.match_repository.create_pending(existing.id)
            if match.parse_status == "completed":
                return ImportResult(
                    record=existing,
                    match=match,
                    deduplicated=True,
                    resolved=resolved,
                    parsed=None,
                )
            parsed, match = self._parse_and_persist(match, resolved)
            return ImportResult(
                record=existing,
                match=match,
                deduplicated=True,
                resolved=resolved,
                parsed=parsed,
            )

        record = self.demo_repository.create(
            digest=digest,
            original_path=resolved.source_path,
            size_bytes=resolved.size_bytes,
        )
        match = self.match_repository.create_pending(record.id)
        parsed, match = self._parse_and_persist(match, resolved)
        return ImportResult(
            record=record,
            match=match,
            deduplicated=False,
            resolved=resolved,
            parsed=parsed,
        )

    def _parse_and_persist(
        self,
        match: MatchRecord,
        resolved: ResolvedDemo,
    ) -> tuple[ParsedDemo | None, MatchRecord]:
        """Parse and persist. Path validation errors stay outside; parse failures
        are recorded on the match row without aborting the import."""
        if not looks_like_pbdems2(resolved.demo_path):
            saved = self.match_repository.save_failed(
                match.id,
                error_code="DEMO_INVALID",
                error_message="File is not a PBDEMS2 CS2 demo.",
                parser_name=getattr(self.parser, "name", None),
                parser_version=(
                    self.parser.version() if hasattr(self.parser, "version") else None
                ),
            )
            return None, saved

        try:
            parsed = self.parser.parse(resolved.demo_path)
            saved = self.match_repository.save_parsed(match.id, parsed)
            return parsed, saved
        except AppError as exc:
            saved = self.match_repository.save_failed(
                match.id,
                error_code=exc.code,
                error_message=exc.message,
                parser_name=getattr(self.parser, "name", None),
                parser_version=(
                    self.parser.version() if hasattr(self.parser, "version") else None
                ),
            )
            return None, saved
        except Exception as exc:  # noqa: BLE001
            saved = self.match_repository.save_failed(
                match.id,
                error_code="PARSER_CRASH",
                error_message=str(exc),
                parser_name=getattr(self.parser, "name", None),
                parser_version=(
                    self.parser.version() if hasattr(self.parser, "version") else None
                ),
            )
            return None, saved
