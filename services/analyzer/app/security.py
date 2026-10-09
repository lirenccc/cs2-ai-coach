from __future__ import annotations

import secrets
from fastapi import Header, HTTPException, status

from .config import Settings


def make_token_verifier(settings: Settings):
    async def verify(
        x_cs2_coach_token: str | None = Header(default=None),
    ) -> None:
        expected = settings.session_token
        if not x_cs2_coach_token or not secrets.compare_digest(
            x_cs2_coach_token.encode("utf-8"),
            expected.encode("utf-8"),
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "UNAUTHORIZED_LOCAL_CLIENT"},
            )

    return verify
