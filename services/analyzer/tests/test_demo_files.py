from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.demo.files import sha256_file, validate_demo_path
from app.errors import DemoInvalidError


def test_valid_demo_and_sha256(tmp_path: Path):
    path = tmp_path / "match.dem"
    payload = b"demo-fixture-content"
    path.write_bytes(payload)

    resolved = validate_demo_path(path)
    assert resolved == path.resolve()
    assert sha256_file(resolved) == hashlib.sha256(payload).hexdigest()


def test_unicode_demo_path_is_supported(tmp_path: Path):
    path = tmp_path / "回放_测试.dem"
    path.write_bytes(b"x")
    assert validate_demo_path(path) == path.resolve()


@pytest.mark.parametrize("name", ["match.txt", "match.demo", "match", "match.dem.exe"])
def test_wrong_extension_is_rejected(tmp_path: Path, name: str):
    path = tmp_path / name
    path.write_bytes(b"x")
    with pytest.raises(DemoInvalidError):
        validate_demo_path(path)


def test_validate_demo_path_still_rejects_zip(tmp_path: Path):
    path = tmp_path / "match.zip"
    path.write_bytes(b"PK\x03\x04")
    with pytest.raises(DemoInvalidError):
        validate_demo_path(path)


def test_missing_demo_is_rejected(tmp_path: Path):
    with pytest.raises(DemoInvalidError):
        validate_demo_path(tmp_path / "missing.dem")


def test_empty_demo_is_rejected(tmp_path: Path):
    path = tmp_path / "empty.dem"
    path.write_bytes(b"")
    with pytest.raises(DemoInvalidError):
        validate_demo_path(path)


@pytest.mark.parametrize("chunk_size", [0, -1])
def test_invalid_hash_chunk_size_is_rejected(tmp_path: Path, chunk_size: int):
    path = tmp_path / "match.dem"
    path.write_bytes(b"x")
    with pytest.raises(ValueError):
        sha256_file(path, chunk_size=chunk_size)
