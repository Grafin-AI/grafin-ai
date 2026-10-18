import hmac

from fastapi import Header, HTTPException, status

from grafin_ai_scoring.config import get_settings


def _verify(authorization: str | None, token: str) -> None:
    """Pure bearer-token check (unit-testable without the HTTP/env layer)."""
    scheme, _, value = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(value.encode(), token.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_token(authorization: str | None = Header(default=None)) -> None:
    """FastAPI dependency: validate the bearer token against the configured secret.

    Reads the token ONLY from settings — nothing request-controllable can override it.
    """
    _verify(authorization, get_settings().scoring_token)
