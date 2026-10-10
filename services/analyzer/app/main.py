from __future__ import annotations

from collections.abc import Callable
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
    MatchReviewResponse,
    ParserHealth,
    ShutdownResponse,
)
from .errors import AppError
from .security import make_token_verifier
from .services.import_demo import ImportDemoService
from .services.match_review import MatchNotFoundError, MatchReviewService
from .storage.db import Database
from .storage.demo_repository import DemoRepository
from .storage.event_repository import EventRepository
from .storage.identity_repository import IdentityRepository
from .storage.match_repository import MatchRepository
from .storage.migrations import migrate
from .storage.persist_parsed import PersistParsedDemoService
from .storage.round_repository import RoundRepository
from .storage.tick_store import JsonTickStore


def create_app(
    settings: Settings | None = None,
    *,
    on_shutdown_request: Callable[[], None] | None = None,
) -> FastAPI:
    settings = settings or Settings()
    settings.ensure_loopback()

    database = Database(Path(settings.db_path))
    migrate(database)
    demo_repo = DemoRepository(database)
    match_repo = MatchRepository(database)
    tick_root = Path(settings.db_path).resolve().parent / "matches"
    persist_parsed = PersistParsedDemoService(
        IdentityRepository(database),
        RoundRepository(database),
        EventRepository(database),
        tick_store=JsonTickStore(tick_root),
    )
    parser = create_demo_parser()
    importer = ImportDemoService(
        demo_repo,
        match_repo,
        parser,
        extract_root=Path(settings.extract_root),
        persist_parsed=persist_parsed,
    )
    review_service = MatchReviewService(match_repo)
    verify = make_token_verifier(settings)

    app = FastAPI(
        title="CS2 AI Coach Analyzer",
        version=__version__,
        docs_url=None,
        redoc_url=None,
    )

    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError):
        status = 404 if isinstance(exc, MatchNotFoundError) else 400
        return JSONResponse(
            status_code=status,
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
        "/v1/shutdown",
        response_model=ShutdownResponse,
        dependencies=[Depends(verify)],
    )
    async def shutdown() -> ShutdownResponse:
        if on_shutdown_request is not None:
            on_shutdown_request()
        return ShutdownResponse()

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

    @app.get(
        "/v1/matches/{match_id}/review",
        response_model=MatchReviewResponse,
        dependencies=[Depends(verify)],
    )
    async def get_match_review(match_id: str) -> MatchReviewResponse:
        payload = review_service.get_review(match_id)
        return MatchReviewResponse.model_validate(payload)

    return app


app = create_app()
