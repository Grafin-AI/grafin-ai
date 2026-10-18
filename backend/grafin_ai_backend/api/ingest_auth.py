import hmac

from fastapi import Header, HTTPException, status

from grafin_ai_backend.config import get_settings


def _verify_ingest(authorization: str | None, token: str) -> None:
    """Pure bearer check for the ingest token (unit-testable without HTTP/env)."""
    scheme, _, value = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(value.encode(), token.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing ingest token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_ingest_token(authorization: str | None = Header(default=None)) -> None:
    """FastAPI dependency: read the ingest token ONLY from settings (no request override)."""
    _verify_ingest(authorization, get_settings().ingest_token)
