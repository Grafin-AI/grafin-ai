import hmac

from fastapi import Header, HTTPException, status

from garda_ai_scoring.config import get_settings


def require_token(
    authorization: str | None = Header(default=None),
    expected: str | None = None,
) -> None:
    """Validate the `Authorization: Bearer <token>` header against the configured token.

    `expected` is injectable for tests; in the app it defaults to the configured token.
    """
    token = get_settings().scoring_token if expected is None else expected
    scheme, _, value = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(value, token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
