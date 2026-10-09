from __future__ import annotations

import hashlib
from pathlib import Path

from ..errors import DemoInvalidError
from .archive import ResolvedDemo, resolve_demo_file, validate_demo_source

__all__ = [
    "ResolvedDemo",
    "resolve_demo_file",
    "sha256_file",
    "validate_demo_path",
    "validate_demo_source",
]


def validate_demo_path(raw: str | Path) -> Path:
    """Validate a raw `.dem` path (not a zip)."""
    path = Path(raw).expanduser()
    if path.suffix.lower() != ".dem":
        raise DemoInvalidError("Expected a .dem file.")
    return validate_demo_source(path)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def looks_like_pbdems2(path: Path) -> bool:
    """Cheap container check before handing bytes to native parsers."""
    try:
        with Path(path).open("rb") as handle:
            magic = handle.read(8)
    except OSError:
        return False
    return magic.startswith(b"PBDEMS2")
