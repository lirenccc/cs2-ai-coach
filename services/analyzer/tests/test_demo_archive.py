from __future__ import annotations

import hashlib
from pathlib import Path
import zipfile

import pytest

from app.demo.archive import resolve_demo_file
from app.demo.files import sha256_file
from app.demo.models import NORMALIZATION_SCHEMA_VERSION, MatchHeader, ParsedDemo
from app.errors import DemoInvalidError
from app.services.import_demo import ImportDemoService
from app.storage.db import Database
from app.storage.demo_repository import DemoRepository
from app.storage.match_repository import MatchRepository
from app.storage.migrations import migrate


class _HashOnlyParser:
    name = "hash-only"

    def available(self) -> bool:
        return True

    def version(self) -> str | None:
        return "0"

    def parse(self, demo_path: Path) -> ParsedDemo:
        return ParsedDemo(
            parser_name=self.name,
            parser_version="0",
            normalization_schema_version=NORMALIZATION_SCHEMA_VERSION,
            header=MatchHeader(map_name="de_dust2"),
            roster=[],
            rounds=[],
            kills=[],
            damages=[],
            source_path=str(demo_path),
        )


def _write_zip(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)


def test_resolve_plain_dem(tmp_path: Path) -> None:
    dem = tmp_path / "match.dem"
    dem.write_bytes(b"plain-demo")
    resolved = resolve_demo_file(dem, extract_root=tmp_path / "extracted")
    assert resolved.from_archive is False
    assert resolved.demo_path == dem.resolve()
    assert resolved.size_bytes == len(b"plain-demo")


def test_resolve_zip_with_single_dem(tmp_path: Path) -> None:
    payload = b"zipped-demo-bytes"
    zip_path = tmp_path / "9208210907649202700_0.zip"
    _write_zip(zip_path, {"9208210907649202700_0.dem": payload})

    resolved = resolve_demo_file(zip_path, extract_root=tmp_path / "extracted")
    assert resolved.from_archive is True
    assert resolved.archive_member == "9208210907649202700_0.dem"
    assert resolved.demo_path.read_bytes() == payload
    assert resolved.demo_path.suffix.lower() == ".dem"
    assert sha256_file(resolved.demo_path) == hashlib.sha256(payload).hexdigest()


def test_zip_and_dem_dedupe_on_content_hash(tmp_path: Path) -> None:
    payload = b"same-demo-content"
    dem = tmp_path / "match.dem"
    dem.write_bytes(payload)
    zip_path = tmp_path / "match.zip"
    _write_zip(zip_path, {"match.dem": payload})

    db = Database(tmp_path / "app.db")
    migrate(db)
    service = ImportDemoService(
        DemoRepository(db),
        MatchRepository(db),
        _HashOnlyParser(),
        extract_root=tmp_path / "extracted",
    )

    first = service.execute(str(zip_path))
    second = service.execute(str(dem))
    assert first.deduplicated is False
    assert second.deduplicated is True
    assert first.record.sha256 == second.record.sha256 == hashlib.sha256(payload).hexdigest()
    assert first.record.original_path.endswith("match.zip")


def test_zip_slip_is_rejected(tmp_path: Path) -> None:
    zip_path = tmp_path / "evil.zip"
    _write_zip(zip_path, {"../escape.dem": b"nope"})
    with pytest.raises(DemoInvalidError):
        resolve_demo_file(zip_path, extract_root=tmp_path / "extracted")


def test_zip_without_dem_is_rejected(tmp_path: Path) -> None:
    zip_path = tmp_path / "emptyish.zip"
    _write_zip(zip_path, {"readme.txt": b"hi"})
    with pytest.raises(DemoInvalidError):
        resolve_demo_file(zip_path, extract_root=tmp_path / "extracted")


def test_multiple_dems_prefer_matching_stem(tmp_path: Path) -> None:
    zip_path = tmp_path / "match.zip"
    _write_zip(
        zip_path,
        {
            "other.dem": b"other",
            "match.dem": b"preferred",
        },
    )
    resolved = resolve_demo_file(zip_path, extract_root=tmp_path / "extracted")
    assert resolved.demo_path.read_bytes() == b"preferred"


def test_ambiguous_multiple_dems_rejected(tmp_path: Path) -> None:
    zip_path = tmp_path / "bundle.zip"
    _write_zip(
        zip_path,
        {
            "a.dem": b"a",
            "b.dem": b"b",
        },
    )
    with pytest.raises(DemoInvalidError):
        resolve_demo_file(zip_path, extract_root=tmp_path / "extracted")
