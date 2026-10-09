from __future__ import annotations

from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CS2_COACH_",
        extra="ignore",
        case_sensitive=False,
    )

    analyzer_host: str = Field(default="127.0.0.1")
    analyzer_port: int = Field(default=8765, ge=1, le=65535)
    session_token: str = Field(default="local-test-token", min_length=8)
    db_path: Path = Field(default=Path("runtime/app.db"))
    extract_root: Path = Field(default=Path("runtime/extracted"))

    def ensure_loopback(self) -> None:
        if self.analyzer_host not in {"127.0.0.1", "localhost"}:
            raise ValueError("Analyzer must bind to loopback.")
