import uuid
from datetime import UTC, datetime, timedelta

import jwt


class InvalidToken(Exception):
    """Raised when a JWT fails signature or expiry validation."""


def _encode(payload: dict, secret: str, algorithm: str = "HS256") -> str:
    return jwt.encode(payload, secret, algorithm=algorithm)


def create_access_token(
    subject: str, role: str, secret: str, ttl_min: int, algorithm: str = "HS256"
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=ttl_min),
    }
    return _encode(payload, secret, algorithm)


def create_refresh_token(
    subject: str, secret: str, ttl_days: int, algorithm: str = "HS256"
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "type": "refresh",
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + timedelta(days=ttl_days),
    }
    return _encode(payload, secret, algorithm)


def decode_token(token: str, secret: str, algorithm: str = "HS256") -> dict:
    try:
        return jwt.decode(token, secret, algorithms=[algorithm])
    except jwt.PyJWTError as exc:
        raise InvalidToken(str(exc)) from exc
