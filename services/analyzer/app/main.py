from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from . import __version__
from .config import Settings
from .demo.factory import create_demo_parser
from .domain.models import (
    HealthResponse,
    ImportDemoRequest,
    ImportDemoResponse,
    ParserHealth,
)
from .errors import AppError
from .security import make_token_verifier
from .services.import_demo import ImportDemoService
from .storage.db import Database
from .storage.demo_repository import DemoRepository
from .storage.match_repository import MatchRepository
from .storage.migrations import migrate


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.ensure_loopback()

    database = Database(Path(settings.db_path))
    migrate(database)
    demo_repo = DemoRepository(database)
    match_repo = MatchRepository(database)
    parser = create_demo_parser()
    importer = ImportDemoService(
        demo_repo,
        match_repo,
        parser,
        extract_root=Path(settings.extract_root),
    )
    verify = make_token_verifier(settings)

    app = FastAPI(
        title="CS2 AI Coach Analyzer",
        version=__version__,
        docs_url=None,
        redoc_url=None,
    )

    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError):
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "retryable": exc.retryable,
                    "details": exc.details or {},
                }
            },
        )

    @app.get("/v1/health", response_model=HealthResponse, dependencies=[Depends(verify)])
    async def health() -> HealthResponse:
        return HealthResponse(
            version=__version__,
            database=str(database.path),
            parser=ParserHealth(
                name=parser.name,
                available=parser.available(),
                version=parser.version(),
            ),
        )

    @app.post(
        "/v1/demos/import",
        response_model=ImportDemoResponse,
        dependencies=[Depends(verify)],
    )
    async def import_demo(request: ImportDemoRequest) -> ImportDemoResponse:
        result = importer.execute(request.path)
        match = result.match
        return ImportDemoResponse(
            demo_id=result.record.id,
            match_id=match.id,
            sha256=result.record.sha256,
            original_path=result.record.original_path,
            deduplicated=result.deduplicated,
            parse_status=match.parse_status,
            map_name=match.map_name,
            parser_name=match.parser_name,
            parser_version=match.parser_version,
            roster_count=match.roster_count,
            round_count=match.round_count,
            kill_count=match.kill_count,
            damage_count=match.damage_count,
        )

    return app


app = create_app()
