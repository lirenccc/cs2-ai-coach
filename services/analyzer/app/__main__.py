from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from .config import Settings
from .main import create_app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--token", required=True)
    parser.add_argument("--db-path", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = Settings(
        analyzer_host=args.host,
        analyzer_port=args.port,
        session_token=args.token,
        db_path=args.db_path,
    )
    settings.ensure_loopback()
    uvicorn.run(
        create_app(settings),
        host=settings.analyzer_host,
        port=settings.analyzer_port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
