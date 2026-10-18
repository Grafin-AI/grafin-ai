from dataclasses import dataclass

from garda_ai_backend.repositories.users import UserRepository
from garda_ai_backend.security.passwords import dummy_verify, verify_password
from garda_ai_backend.security.refresh_store import RefreshTokenStore
from garda_ai_backend.security.tokens import (
    InvalidToken,
    create_access_token,
    create_refresh_token,
    decode_token,
)


class AuthError(Exception):
    """Authentication or token-refresh failure."""


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str


class AuthService:
    def __init__(
        self,
        users: UserRepository,
        refresh_store: RefreshTokenStore,
        secret: str,
        access_ttl_min: int,
        refresh_ttl_days: int,
    ) -> None:
        self._users = users
        self._refresh_store = refresh_store
        self._secret = secret
        self._access_ttl_min = access_ttl_min
        self._refresh_ttl_days = refresh_ttl_days

    async def _issue(self, user_id: str, role: str) -> TokenPair:
        access = create_access_token(
            subject=user_id, role=role, secret=self._secret, ttl_min=self._access_ttl_min
        )
        refresh = create_refresh_token(
            subject=user_id, secret=self._secret, ttl_days=self._refresh_ttl_days
        )
        claims = decode_token(refresh, secret=self._secret)
        await self._refresh_store.save(
            jti=claims["jti"], user_id=user_id, ttl_seconds=self._refresh_ttl_days * 86400
        )
        return TokenPair(access_token=access, refresh_token=refresh)

    async def authenticate(self, email: str, password: str) -> TokenPair:
        user = await self._users.get_by_email(email)
        if user is None:
            dummy_verify()  # equalize timing to avoid user enumeration
            raise AuthError("invalid credentials")
        if not verify_password(password, user.password_hash):
            raise AuthError("invalid credentials")
        return await self._issue(str(user.id), user.role)

    async def refresh(self, refresh_token: str) -> TokenPair:
        try:
            claims = decode_token(refresh_token, secret=self._secret)
        except InvalidToken as exc:
            raise AuthError("invalid refresh token") from exc
        if claims.get("type") != "refresh":
            raise AuthError("not a refresh token")
        user_id = claims["sub"]
        # Atomic single-use consume: closes the validate-then-revoke replay race.
        if not await self._refresh_store.consume(claims["jti"], user_id):
            raise AuthError("refresh token revoked or unknown")
        user = await self._users.get_by_id(int(user_id))
        if user is None:
            raise AuthError("user no longer exists")
        return await self._issue(str(user.id), user.role)

    async def logout(self, refresh_token: str) -> None:
        try:
            claims = decode_token(refresh_token, secret=self._secret)
        except InvalidToken:
            return
        if claims.get("type") == "refresh" and "jti" in claims:
            await self._refresh_store.revoke(claims["jti"])
