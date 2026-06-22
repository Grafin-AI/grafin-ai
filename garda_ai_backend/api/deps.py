from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from garda_ai_backend.config import Settings, get_settings
from garda_ai_backend.db import _maker
from garda_ai_backend.redis_client import get_redis
from garda_ai_backend.repositories.sim import SimRepository
from garda_ai_backend.repositories.users import UserRepository
from garda_ai_backend.security.refresh_store import RefreshTokenStore
from garda_ai_backend.security.tokens import InvalidToken, decode_token
from garda_ai_backend.services.auth import AuthService


@dataclass(frozen=True)
class CurrentUser:
    id: int
    role: str


async def get_session() -> AsyncIterator[AsyncSession]:
    async with _maker()() as session:
        yield session


def get_redis_dep() -> Redis:
    return get_redis()


def get_settings_dep() -> Settings:
    return get_settings()


SessionDep = Annotated[AsyncSession, Depends(get_session)]
RedisDep = Annotated[Redis, Depends(get_redis_dep)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]


def get_auth_service(
    session: SessionDep, redis: RedisDep, settings: SettingsDep
) -> AuthService:
    return AuthService(
        users=UserRepository(session),
        refresh_store=RefreshTokenStore(redis),
        secret=settings.jwt_secret,
        access_ttl_min=settings.jwt_access_ttl_min,
        refresh_ttl_days=settings.jwt_refresh_ttl_days,
    )


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]

_bearer = HTTPBearer(auto_error=True)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    settings: SettingsDep,
) -> CurrentUser:
    try:
        claims = decode_token(credentials.credentials, secret=settings.jwt_secret)
    except InvalidToken:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token"
        ) from None
    if claims.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="not an access token"
        )
    return CurrentUser(id=int(claims["sub"]), role=claims["role"])


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


async def get_sim_now(session: SessionDep) -> datetime:
    """Shared dependency: the simulation clock, or 404 if uninitialized.

    Every view aggregate filters `surfaced_at <= sim_now`; this is the one
    typed source so view routers don't each re-implement the lookup.
    """
    sim_now = await SimRepository(session).get_sim_now()
    if sim_now is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="sim not initialized"
        )
    return sim_now


SimNowDep = Annotated[datetime, Depends(get_sim_now)]


def require_role(*roles: str) -> Callable[[CurrentUser], CurrentUser]:
    def guard(user: CurrentUserDep) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="insufficient role"
            )
        return user

    return guard
