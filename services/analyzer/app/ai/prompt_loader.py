"""Load versioned AI prompts from the local prompts directory."""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path


PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


class UnknownPromptVersionError(ValueError):
    pass


@lru_cache(maxsize=16)
def load_prompt(prompt_version: str) -> tuple[str, str]:
    """Return `(prompt_text, prompt_sha256)` for a version id like `provider_smoke_v001`."""
    path = PROMPTS_DIR / f"{prompt_version}.md"
    if not path.is_file():
        raise UnknownPromptVersionError(f"Unknown prompt version: {prompt_version}")
    text = path.read_text(encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return text, digest
