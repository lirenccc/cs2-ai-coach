"""Privacy helpers for AI request logging (no secrets / private paths / image bytes)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


_ABS_PATH_RE = re.compile(
    r"(?i)(?:[a-z]:\\|\\\\|/home/|/Users/|/var/|/tmp/)[^\s\"']+"
)
_DATA_URL_RE = re.compile(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]+")
_STEAM_ID_RE = re.compile(r"\b7656119\d{10}\b")
_API_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9_\-]{10,}\b")


def redact_path_for_logs(path: Path | str) -> str:
    """Keep only a stable basename-ish label; drop private absolute parents."""
    p = Path(path)
    parent = p.parent.name if p.parent.name else "dir"
    return f"<redacted>/{parent}/{p.name}"


def sanitize_log_text(text: str) -> str:
    cleaned = _DATA_URL_RE.sub("data:image/<redacted>;base64,<redacted>", text)
    cleaned = _API_KEY_RE.sub("sk-<redacted>", cleaned)
    cleaned = _STEAM_ID_RE.sub("<steamid-redacted>", cleaned)
    cleaned = _ABS_PATH_RE.sub("<absolute-path-redacted>", cleaned)
    return cleaned


def safe_request_log_fields(
    *,
    request_fingerprint: str,
    model: str,
    prompt_version: str,
    schema_version: str,
    ai_contract_version: str,
    evidence_ids: list[str],
    frame_ids: list[str],
    frame_sha256s: list[str],
    frame_dimensions: list[tuple[int | None, int | None]],
    image_detail: str,
    store: bool,
    latency_ms: int | None = None,
    validation_ok: bool | None = None,
    usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "request_fingerprint": request_fingerprint,
        "model": model,
        "prompt_version": prompt_version,
        "schema_version": schema_version,
        "ai_contract_version": ai_contract_version,
        "evidence_ids": list(evidence_ids),
        "frame_ids": list(frame_ids),
        "frame_sha256s": list(frame_sha256s),
        "frame_dimensions": [
            {"width": width, "height": height} for width, height in frame_dimensions
        ],
        "image_detail": image_detail,
        "store": store,
        "latency_ms": latency_ms,
        "validation_ok": validation_ok,
        "usage": usage,
    }
