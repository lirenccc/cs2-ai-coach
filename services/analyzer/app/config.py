from __future__ import annotations

from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# services/analyzer/app/config.py → repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
_REPO_ENV = _REPO_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CS2_COACH_",
        env_file=str(_REPO_ENV) if _REPO_ENV.is_file() else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    analyzer_host: str = Field(default="127.0.0.1")
    analyzer_port: int = Field(default=8765, ge=1, le=65535)
    session_token: str = Field(default="local-test-token", min_length=8)
    db_path: Path = Field(default=Path("runtime/app.db"))
    extract_root: Path = Field(default=Path("runtime/extracted"))

    # Analyzer/backend-only AI credentials (never expose to renderer).
    openai_api_key: str | None = Field(default=None)
    openai_base_url: str | None = Field(default=None)
    ai_model: str = Field(default="gpt-4o-mini")
    ai_image_detail: str = Field(default="auto")
    ai_real_smoke: bool = Field(default=False)
    ai_smoke_frame: Path | None = Field(default=None)

    def ensure_loopback(self) -> None:
        if self.analyzer_host not in {"127.0.0.1", "localhost"}:
            raise ValueError("Analyzer must bind to loopback.")
