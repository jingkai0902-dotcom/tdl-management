from __future__ import annotations

import hmac

from fastapi import HTTPException, Request, status

from app.config import get_settings


INTERNAL_API_KEY_HEADER = "X-TDL-Internal-Key"


def require_internal_api_key(request: Request) -> None:
    settings = get_settings()
    expected_key = settings.internal_api_key
    if not expected_key:
        if settings.app_env == "development":
            return
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal API key is not configured",
        )

    provided_key = request.headers.get(INTERNAL_API_KEY_HEADER)
    if not provided_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing internal API key",
        )
    if not hmac.compare_digest(provided_key, expected_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid internal API key",
        )
