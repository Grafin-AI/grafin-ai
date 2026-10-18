from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from grafin_ai_backend.api.deps import (
    AuthServiceDep,
    CurrentUserDep,
    RedisDep,
    SessionDep,
)
from grafin_ai_backend.api.ratelimit import RateLimiter
from grafin_ai_backend.api.schemas import (
    LoginRequest,
    MeResponse,
    RefreshRequest,
    TokenResponse,
)
from grafin_ai_backend.repositories.users import UserRepository
from grafin_ai_backend.services.auth import AuthError

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_LOGIN_LIMIT = 10
_LOGIN_WINDOW_SECONDS = 60


async def login_rate_limit(request: Request, redis: RedisDep) -> None:
    client = request.client.host if request.client else "unknown"
    limiter = RateLimiter(redis, limit=_LOGIN_LIMIT, window_seconds=_LOGIN_WINDOW_SECONDS)
    await limiter.check(f"login:{client}")


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(login_rate_limit)])
async def login(body: LoginRequest, auth: AuthServiceDep) -> TokenResponse:
    try:
        pair = await auth.authenticate(body.email, body.password)
    except AuthError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials"
        ) from None
    return TokenResponse(access_token=pair.access_token, refresh_token=pair.refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, auth: AuthServiceDep) -> TokenResponse:
    try:
        pair = await auth.refresh(body.refresh_token)
    except AuthError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid refresh token"
        ) from None
    return TokenResponse(access_token=pair.access_token, refresh_token=pair.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshRequest, auth: AuthServiceDep) -> Response:
    await auth.logout(body.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=MeResponse)
async def me(user: CurrentUserDep, session: SessionDep) -> MeResponse:
    db_user = await UserRepository(session).get_by_id(user.id)
    if db_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    return MeResponse(id=db_user.id, email=db_user.email, role=db_user.role)
