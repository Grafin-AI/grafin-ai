# Backend Auth, RBAC & Redis Foundation Implementation Plan (Plan 2A)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the security layer to `grafin-ai-backend` — Redis integration, Argon2id passwords, JWT access/refresh with a revocable Redis-backed refresh store, the `/auth` endpoints, RBAC dependencies (`get_current_user`, `require_role`), auth-endpoint rate limiting, and a seed script (bootstrap admin + `sim_state` row). This unblocks all protected view endpoints (Plan 2B) and the WS relay (Plan 2C).

**Architecture:** Layered per the spec — `api/` (routers + deps) → `services/` (use cases) → `repositories/` (DB access) → `security/` (passwords, tokens, refresh store) → `schema/` (existing models). No business logic in routers; no raw SQL outside repositories. Builds on Plan 1's `config.get_settings`, `db._maker/get_session`, and `schema.User`.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, `redis.asyncio`, PyJWT, argon2-cffi, Pydantic v2 (+ email-validator), pytest + testcontainers (Postgres + Redis).

---

## File structure (created/modified by this plan)

```
grafin_ai_backend/
├── config.py                      # MODIFY: add redis_url, jwt_secret, jwt_access_ttl_min, jwt_refresh_ttl_days
├── redis_client.py                # CREATE: build_redis + lazy get_redis()
├── main.py                        # MODIFY: include auth router; /readyz also pings Redis
├── security/
│   ├── __init__.py
│   ├── passwords.py               # CREATE: hash_password / verify_password (argon2)
│   ├── tokens.py                  # CREATE: create_access_token / create_refresh_token / decode_token
│   └── refresh_store.py           # CREATE: RefreshTokenStore (Redis; save/is_valid/revoke)
├── repositories/
│   ├── __init__.py
│   └── users.py                   # CREATE: UserRepository (get_by_email, get_by_id, create)
├── services/
│   ├── __init__.py
│   └── auth.py                    # CREATE: AuthService (authenticate, issue, refresh, logout)
├── api/
│   ├── __init__.py
│   ├── schemas.py                 # CREATE: Pydantic request/response models for auth
│   ├── deps.py                    # CREATE: db/redis/service providers, get_current_user, require_role
│   ├── ratelimit.py               # CREATE: Redis fixed-window rate-limit dependency
│   └── auth.py                    # CREATE: /api/v1/auth router (login, refresh, logout, me)
└── seed.py                        # CREATE: bootstrap admin user + sim_state singleton row
tests/
├── conftest.py                    # MODIFY: add redis_url fixture + env defaults (REDIS_URL, JWT_SECRET)
├── test_passwords.py
├── test_tokens.py
├── test_users_repo.py
├── test_refresh_store.py
├── test_auth_service.py
├── test_auth_api.py
├── test_ratelimit.py
└── test_seed.py
```

---

### Task 1: Config + dependencies for Redis & JWT

**Files:**
- Modify: `pyproject.toml`
- Modify: `grafin_ai_backend/config.py`
- Test: `tests/test_config.py` (add case)

- [ ] **Step 1: Add runtime deps**

Add to `[project].dependencies` in `pyproject.toml` (keep existing entries):
```toml
    "redis>=5.2",
    "pyjwt>=2.10",
    "argon2-cffi>=23.1",
    "email-validator>=2.2",
```
Add to `[dependency-groups].dev` (keep existing): `"testcontainers[postgres,redis]>=4.8"` (replace the existing `testcontainers[postgres]>=4.8` line with this extras form).

- [ ] **Step 2: Write the failing test**

Append to `tests/test_config.py`:
```python
def test_settings_auth_fields(monkeypatch):
    monkeypatch.setenv("GRAFIN_DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/d")
    monkeypatch.setenv("GRAFIN_REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("GRAFIN_JWT_SECRET", "test-secret")
    from grafin_ai_backend.config import Settings
    s = Settings()
    assert s.redis_url == "redis://localhost:6379/0"
    assert s.jwt_secret == "test-secret"
    assert s.jwt_access_ttl_min == 15      # default
    assert s.jwt_refresh_ttl_days == 7     # default
    assert s.jwt_algorithm == "HS256"      # default
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py::test_settings_auth_fields -v`
Expected: FAIL (`AttributeError`/validation error — fields not defined).

- [ ] **Step 4: Extend `Settings`**

In `grafin_ai_backend/config.py`, add fields to the `Settings` class (after `log_level`):
```python
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me-in-prod"
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_min: int = 15
    jwt_refresh_ttl_days: int = 7
```

- [ ] **Step 5: Sync + run test**

Run: `uv sync` then `uv run pytest tests/test_config.py -v`
Expected: PASS (all config tests).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock grafin_ai_backend/config.py tests/test_config.py
git commit -m "feat: add redis + jwt settings and auth dependencies"
```

---

### Task 2: Redis client + conftest fixtures

**Files:**
- Create: `grafin_ai_backend/redis_client.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_redis_client.py`

- [ ] **Step 1: Extend conftest with a Redis container + env defaults**

In `tests/conftest.py`, add the two env defaults right after the existing `GRAFIN_DATABASE_URL` setdefault:
```python
os.environ.setdefault("GRAFIN_REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("GRAFIN_JWT_SECRET", "test-secret")
```
Add these imports near the top (with the existing imports):
```python
from redis.asyncio import Redis
from testcontainers.redis import RedisContainer
```
Add these fixtures at the end of the file:
```python
@pytest.fixture(scope="session")
def redis_url():
    with RedisContainer("redis:7-alpine") as rc:
        host = rc.get_container_host_ip()
        port = rc.get_exposed_port(6379)
        yield f"redis://{host}:{port}/0"


@pytest_asyncio.fixture
async def redis_client(redis_url):
    client = Redis.from_url(redis_url, decode_responses=True)
    await client.flushdb()
    yield client
    await client.aclose()
```

- [ ] **Step 2: Write the failing test**

`tests/test_redis_client.py`:
```python
from grafin_ai_backend.redis_client import build_redis


async def test_build_redis_pings(redis_url):
    client = build_redis(redis_url)
    assert await client.ping() is True
    await client.aclose()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_redis_client.py -v`
Expected: FAIL (`ModuleNotFoundError: grafin_ai_backend.redis_client`).

- [ ] **Step 4: Implement the client**

`grafin_ai_backend/redis_client.py`:
```python
from redis.asyncio import Redis

from grafin_ai_backend.config import get_settings


def build_redis(url: str) -> Redis:
    return Redis.from_url(url, decode_responses=True)


_redis: Redis | None = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = build_redis(get_settings().redis_url)
    return _redis
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_redis_client.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add grafin_ai_backend/redis_client.py tests/conftest.py tests/test_redis_client.py
git commit -m "feat: async redis client + testcontainers redis fixture"
```

---

### Task 3: Password hashing (Argon2id)

**Files:**
- Create: `grafin_ai_backend/security/__init__.py`, `grafin_ai_backend/security/passwords.py`
- Test: `tests/test_passwords.py`

- [ ] **Step 1: Write the failing test**

`tests/test_passwords.py`:
```python
from grafin_ai_backend.security.passwords import hash_password, verify_password


def test_hash_and_verify():
    h = hash_password("s3cret!")
    assert h != "s3cret!"
    assert h.startswith("$argon2")
    assert verify_password("s3cret!", h) is True
    assert verify_password("wrong", h) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_passwords.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

`grafin_ai_backend/security/__init__.py`:
```python
```
(empty file)

`grafin_ai_backend/security/passwords.py`:
```python
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_ph = PasswordHasher()


def hash_password(plain: str) -> str:
    return _ph.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, plain)
    except VerifyMismatchError:
        return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_passwords.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add grafin_ai_backend/security/ tests/test_passwords.py
git commit -m "feat: argon2id password hashing"
```

---

### Task 4: JWT tokens

**Files:**
- Create: `grafin_ai_backend/security/tokens.py`
- Test: `tests/test_tokens.py`

- [ ] **Step 1: Write the failing test**

`tests/test_tokens.py`:
```python
import pytest

from grafin_ai_backend.security.tokens import (
    InvalidToken,
    create_access_token,
    create_refresh_token,
    decode_token,
)

SECRET = "test-secret"


def test_access_token_roundtrip():
    token = create_access_token(subject="7", role="analyst", secret=SECRET, ttl_min=15)
    claims = decode_token(token, secret=SECRET)
    assert claims["sub"] == "7"
    assert claims["role"] == "analyst"
    assert claims["type"] == "access"


def test_refresh_token_has_jti_and_type():
    token = create_refresh_token(subject="7", secret=SECRET, ttl_days=7)
    claims = decode_token(token, secret=SECRET)
    assert claims["type"] == "refresh"
    assert "jti" in claims


def test_decode_rejects_bad_signature():
    token = create_access_token(subject="7", role="analyst", secret=SECRET, ttl_min=15)
    with pytest.raises(InvalidToken):
        decode_token(token, secret="other-secret")


def test_decode_rejects_expired():
    token = create_access_token(subject="7", role="analyst", secret=SECRET, ttl_min=-1)
    with pytest.raises(InvalidToken):
        decode_token(token, secret=SECRET)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tokens.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

`grafin_ai_backend/security/tokens.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_tokens.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add grafin_ai_backend/security/tokens.py tests/test_tokens.py
git commit -m "feat: jwt access/refresh token creation + validation"
```

---

### Task 5: Users repository

**Files:**
- Create: `grafin_ai_backend/repositories/__init__.py`, `grafin_ai_backend/repositories/users.py`
- Test: `tests/test_users_repo.py`

- [ ] **Step 1: Write the failing test**

`tests/test_users_repo.py`:
```python
from datetime import UTC, datetime

from grafin_ai_backend.repositories.users import UserRepository


async def test_create_and_fetch_user(session):
    repo = UserRepository(session)
    user = await repo.create(
        email="a@example.com",
        password_hash="$argon2id$hash",
        role="analyst",
        created_at=datetime.now(UTC),
    )
    await session.commit()
    assert user.id is not None

    by_email = await repo.get_by_email("a@example.com")
    assert by_email is not None
    assert by_email.role == "analyst"

    by_id = await repo.get_by_id(user.id)
    assert by_id is not None
    assert by_id.email == "a@example.com"

    missing = await repo.get_by_email("none@example.com")
    assert missing is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_users_repo.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

`grafin_ai_backend/repositories/__init__.py`:
```python
```
(empty file)

`grafin_ai_backend/repositories/users.py`:
```python
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grafin_ai_backend.schema import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> User | None:
        return await self._session.get(User, user_id)

    async def create(
        self, email: str, password_hash: str, role: str, created_at: datetime
    ) -> User:
        user = User(
            email=email, password_hash=password_hash, role=role, created_at=created_at
        )
        self._session.add(user)
        await self._session.flush()
        return user
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_users_repo.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add grafin_ai_backend/repositories/ tests/test_users_repo.py
git commit -m "feat: users repository (get_by_email/get_by_id/create)"
```

---

### Task 6: Refresh-token store (Redis, revocable)

**Files:**
- Create: `grafin_ai_backend/security/refresh_store.py`
- Test: `tests/test_refresh_store.py`

- [ ] **Step 1: Write the failing test**

`tests/test_refresh_store.py`:
```python
from grafin_ai_backend.security.refresh_store import RefreshTokenStore


async def test_save_validate_revoke(redis_client):
    store = RefreshTokenStore(redis_client)
    await store.save(jti="jti-1", user_id="7", ttl_seconds=60)

    assert await store.is_valid(jti="jti-1", user_id="7") is True
    assert await store.is_valid(jti="jti-1", user_id="9") is False  # wrong user
    assert await store.is_valid(jti="missing", user_id="7") is False

    await store.revoke(jti="jti-1")
    assert await store.is_valid(jti="jti-1", user_id="7") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_refresh_store.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

`grafin_ai_backend/security/refresh_store.py`:
```python
from redis.asyncio import Redis


class RefreshTokenStore:
    """Stores valid refresh-token jtis in Redis so they can be revoked."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    @staticmethod
    def _key(jti: str) -> str:
        return f"refresh:{jti}"

    async def save(self, jti: str, user_id: str, ttl_seconds: int) -> None:
        await self._redis.set(self._key(jti), user_id, ex=ttl_seconds)

    async def is_valid(self, jti: str, user_id: str) -> bool:
        stored = await self._redis.get(self._key(jti))
        return stored is not None and stored == user_id

    async def revoke(self, jti: str) -> None:
        await self._redis.delete(self._key(jti))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_refresh_store.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add grafin_ai_backend/security/refresh_store.py tests/test_refresh_store.py
git commit -m "feat: redis-backed revocable refresh-token store"
```

---

### Task 7: Auth service

**Files:**
- Create: `grafin_ai_backend/services/__init__.py`, `grafin_ai_backend/services/auth.py`
- Test: `tests/test_auth_service.py`

- [ ] **Step 1: Write the failing test**

`tests/test_auth_service.py`:
```python
from datetime import UTC, datetime

import pytest

from grafin_ai_backend.repositories.users import UserRepository
from grafin_ai_backend.security.passwords import hash_password
from grafin_ai_backend.security.refresh_store import RefreshTokenStore
from grafin_ai_backend.security.tokens import decode_token
from grafin_ai_backend.services.auth import AuthError, AuthService

SECRET = "test-secret"


async def _seed_user(session, email="a@example.com", password="pw", role="analyst"):
    repo = UserRepository(session)
    await repo.create(
        email=email, password_hash=hash_password(password), role=role,
        created_at=datetime.now(UTC),
    )
    await session.commit()


def _service(session, redis_client):
    return AuthService(
        users=UserRepository(session),
        refresh_store=RefreshTokenStore(redis_client),
        secret=SECRET,
        access_ttl_min=15,
        refresh_ttl_days=7,
    )


async def test_authenticate_issues_tokens(session, redis_client):
    await _seed_user(session)
    svc = _service(session, redis_client)
    pair = await svc.authenticate("a@example.com", "pw")
    access = decode_token(pair.access_token, secret=SECRET)
    assert access["role"] == "analyst"
    refresh = decode_token(pair.refresh_token, secret=SECRET)
    assert await RefreshTokenStore(redis_client).is_valid(refresh["jti"], access["sub"])


async def test_authenticate_bad_password(session, redis_client):
    await _seed_user(session)
    svc = _service(session, redis_client)
    with pytest.raises(AuthError):
        await svc.authenticate("a@example.com", "wrong")


async def test_refresh_rotates_and_revokes_old(session, redis_client):
    await _seed_user(session)
    svc = _service(session, redis_client)
    pair = await svc.authenticate("a@example.com", "pw")
    old_jti = decode_token(pair.refresh_token, secret=SECRET)["jti"]
    new_pair = await svc.refresh(pair.refresh_token)
    # old refresh now revoked, new one valid
    assert await RefreshTokenStore(redis_client).is_valid(old_jti, "1") is False
    new_claims = decode_token(new_pair.refresh_token, secret=SECRET)
    assert await RefreshTokenStore(redis_client).is_valid(new_claims["jti"], "1")


async def test_logout_revokes(session, redis_client):
    await _seed_user(session)
    svc = _service(session, redis_client)
    pair = await svc.authenticate("a@example.com", "pw")
    jti = decode_token(pair.refresh_token, secret=SECRET)["jti"]
    await svc.logout(pair.refresh_token)
    assert await RefreshTokenStore(redis_client).is_valid(jti, "1") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_auth_service.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

`grafin_ai_backend/services/__init__.py`:
```python
```
(empty file)

`grafin_ai_backend/services/auth.py`:
```python
from dataclasses import dataclass

from grafin_ai_backend.repositories.users import UserRepository
from grafin_ai_backend.security.passwords import verify_password
from grafin_ai_backend.security.refresh_store import RefreshTokenStore
from grafin_ai_backend.security.tokens import (
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
        if user is None or not verify_password(password, user.password_hash):
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
        if not await self._refresh_store.is_valid(claims["jti"], user_id):
            raise AuthError("refresh token revoked or unknown")
        await self._refresh_store.revoke(claims["jti"])  # rotation
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_auth_service.py -v`
Expected: PASS (4 tests). (Seeded user gets `id=1`, hence the `"1"` assertions.)

- [ ] **Step 5: Commit**

```bash
git add grafin_ai_backend/services/ tests/test_auth_service.py
git commit -m "feat: auth service (authenticate, refresh rotation, logout)"
```

---

### Task 8: API schemas + dependencies (current user, RBAC)

**Files:**
- Create: `grafin_ai_backend/api/__init__.py`, `grafin_ai_backend/api/schemas.py`, `grafin_ai_backend/api/deps.py`
- Test: `tests/test_deps.py`

- [ ] **Step 1: Write the failing test**

`tests/test_deps.py`:
```python
import pytest
from fastapi import HTTPException

from grafin_ai_backend.api.deps import CurrentUser, require_role


def _user(role: str) -> CurrentUser:
    return CurrentUser(id=1, role=role)


def test_require_role_allows_match():
    guard = require_role("analyst", "admin")
    assert guard(_user("analyst")) is not None
    assert guard(_user("admin")).role == "admin"


def test_require_role_blocks_others():
    guard = require_role("admin")
    with pytest.raises(HTTPException) as exc:
        guard(_user("analyst"))
    assert exc.value.status_code == 403
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_deps.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement schemas**

`grafin_ai_backend/api/__init__.py`:
```python
```
(empty file)

`grafin_ai_backend/api/schemas.py`:
```python
from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    id: int
    email: EmailStr
    role: str
```

- [ ] **Step 4: Implement dependencies**

`grafin_ai_backend/api/deps.py`:
```python
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated, Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from grafin_ai_backend.config import Settings, get_settings
from grafin_ai_backend.db import _maker
from grafin_ai_backend.redis_client import get_redis
from grafin_ai_backend.repositories.users import UserRepository
from grafin_ai_backend.security.refresh_store import RefreshTokenStore
from grafin_ai_backend.security.tokens import InvalidToken, decode_token
from grafin_ai_backend.services.auth import AuthService


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


def require_role(*roles: str) -> Callable[[CurrentUser], CurrentUser]:
    def guard(user: CurrentUserDep) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="insufficient role"
            )
        return user

    return guard
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_deps.py -v`
Expected: PASS. (The unit test calls the inner `guard` with a `CurrentUser` directly, bypassing FastAPI injection.)

- [ ] **Step 6: Commit**

```bash
git add grafin_ai_backend/api/__init__.py grafin_ai_backend/api/schemas.py grafin_ai_backend/api/deps.py tests/test_deps.py
git commit -m "feat: api schemas + DI providers + get_current_user/require_role"
```

---

### Task 9: Rate-limit dependency (Redis fixed window)

**Files:**
- Create: `grafin_ai_backend/api/ratelimit.py`
- Test: `tests/test_ratelimit.py`

- [ ] **Step 1: Write the failing test**

`tests/test_ratelimit.py`:
```python
import pytest
from fastapi import HTTPException

from grafin_ai_backend.api.ratelimit import RateLimiter


async def test_allows_under_limit(redis_client):
    rl = RateLimiter(redis_client, limit=3, window_seconds=60)
    for _ in range(3):
        await rl.check("client-a")  # no raise


async def test_blocks_over_limit(redis_client):
    rl = RateLimiter(redis_client, limit=2, window_seconds=60)
    await rl.check("client-b")
    await rl.check("client-b")
    with pytest.raises(HTTPException) as exc:
        await rl.check("client-b")
    assert exc.value.status_code == 429


async def test_separate_keys_independent(redis_client):
    rl = RateLimiter(redis_client, limit=1, window_seconds=60)
    await rl.check("client-c")
    await rl.check("client-d")  # different key, allowed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ratelimit.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

`grafin_ai_backend/api/ratelimit.py`:
```python
from fastapi import HTTPException, status
from redis.asyncio import Redis


class RateLimiter:
    """Fixed-window per-key limiter backed by Redis INCR + EXPIRE."""

    def __init__(self, redis: Redis, limit: int, window_seconds: int) -> None:
        self._redis = redis
        self._limit = limit
        self._window = window_seconds

    async def check(self, key: str) -> None:
        redis_key = f"ratelimit:{key}"
        count = await self._redis.incr(redis_key)
        if count == 1:
            await self._redis.expire(redis_key, self._window)
        if count > self._limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="rate limit exceeded",
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ratelimit.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add grafin_ai_backend/api/ratelimit.py tests/test_ratelimit.py
git commit -m "feat: redis fixed-window rate limiter"
```

---

### Task 10: Auth router wired into the app

**Files:**
- Create: `grafin_ai_backend/api/auth.py`
- Modify: `grafin_ai_backend/main.py`
- Test: `tests/test_auth_api.py`

- [ ] **Step 1: Write the failing integration test**

`tests/test_auth_api.py`:
```python
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from grafin_ai_backend.api import deps
from grafin_ai_backend.redis_client import build_redis
from grafin_ai_backend.repositories.users import UserRepository
from grafin_ai_backend.security.passwords import hash_password


@pytest_asyncio.fixture
async def client(session, redis_url, monkeypatch):
    # Point the app's dependencies at the test Postgres session + test Redis.
    async def _override_session():
        yield session

    test_redis = build_redis(redis_url)
    monkeypatch.setattr(deps, "get_redis", lambda: test_redis)

    # Seed an analyst user (id=1)
    repo = UserRepository(session)
    await repo.create(
        email="analyst@example.com", password_hash=hash_password("pw"),
        role="analyst", created_at=datetime.now(UTC),
    )
    await session.commit()

    from grafin_ai_backend.main import app
    app.dependency_overrides[deps.get_session] = _override_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    await test_redis.aclose()


async def test_login_me_refresh_logout_flow(client):
    # login
    r = await client.post(
        "/api/v1/auth/login", json={"email": "analyst@example.com", "password": "pw"}
    )
    assert r.status_code == 200
    tokens = r.json()
    access, refresh = tokens["access_token"], tokens["refresh_token"]

    # me (authorized)
    r = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200
    assert r.json()["email"] == "analyst@example.com"
    assert r.json()["role"] == "analyst"

    # me without token -> 403 (HTTPBearer auto_error) 
    r = await client.get("/api/v1/auth/me")
    assert r.status_code in (401, 403)

    # refresh
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 200
    new_refresh = r.json()["refresh_token"]

    # old refresh now rejected
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 401

    # logout new refresh
    r = await client.post("/api/v1/auth/logout", json={"refresh_token": new_refresh})
    assert r.status_code == 204


async def test_login_bad_credentials(client):
    r = await client.post(
        "/api/v1/auth/login", json={"email": "analyst@example.com", "password": "nope"}
    )
    assert r.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_auth_api.py -v`
Expected: FAIL (router not present → 404, or import error).

- [ ] **Step 3: Implement the router**

`grafin_ai_backend/api/auth.py`:
```python
from fastapi import APIRouter, HTTPException, Response, status

from grafin_ai_backend.api.deps import AuthServiceDep, CurrentUserDep, SessionDep
from grafin_ai_backend.api.schemas import (
    LoginRequest,
    MeResponse,
    RefreshRequest,
    TokenResponse,
)
from grafin_ai_backend.repositories.users import UserRepository
from grafin_ai_backend.services.auth import AuthError

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
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
```

- [ ] **Step 4: Wire the router + Redis readiness into `main.py`**

In `grafin_ai_backend/main.py`, add the import and `include_router`, and extend `/readyz` to also ping Redis. Replace the file body with:
```python
from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from grafin_ai_backend.api.auth import router as auth_router
from grafin_ai_backend.config import get_settings
from grafin_ai_backend.db import _maker
from grafin_ai_backend.observability import REGISTRY, configure_logging
from grafin_ai_backend.redis_client import get_redis

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(title="Grafin AI Backend", version="0.1.0")
app.include_router(auth_router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> Response:
    try:
        async with _maker()() as session:
            await session.execute(text("SELECT 1"))
        await get_redis().ping()
        return Response(content='{"status":"ready"}', media_type="application/json")
    except Exception:
        return Response(
            content='{"status":"not-ready"}', media_type="application/json", status_code=503
        )


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_auth_api.py -v`
Expected: PASS (both tests). Then run `uv run pytest -v` (full suite green).

- [ ] **Step 6: Commit**

```bash
git add grafin_ai_backend/api/auth.py grafin_ai_backend/main.py tests/test_auth_api.py
git commit -m "feat: /api/v1/auth router (login/refresh/logout/me); redis readiness"
```

---

### Task 11: Seed script (bootstrap admin + sim_state)

**Files:**
- Create: `grafin_ai_backend/seed.py`
- Test: `tests/test_seed.py`

- [ ] **Step 1: Write the failing test**

`tests/test_seed.py`:
```python
from datetime import UTC, datetime

from sqlalchemy import select

from grafin_ai_backend.repositories.users import UserRepository
from grafin_ai_backend.schema import SimState
from grafin_ai_backend.seed import ensure_admin, ensure_sim_state


async def test_ensure_admin_is_idempotent(session):
    u1 = await ensure_admin(session, "admin@example.com", "pw")
    await session.commit()
    u2 = await ensure_admin(session, "admin@example.com", "pw")
    await session.commit()
    assert u1.id == u2.id  # not duplicated
    assert u1.role == "admin"
    found = await UserRepository(session).get_by_email("admin@example.com")
    assert found is not None


async def test_ensure_sim_state_singleton(session):
    s1 = await ensure_sim_state(session, start=datetime(2025, 9, 1, tzinfo=UTC), speed=60.0)
    await session.commit()
    await ensure_sim_state(session, start=datetime(2025, 9, 1, tzinfo=UTC), speed=60.0)
    await session.commit()
    rows = (await session.execute(select(SimState))).scalars().all()
    assert len(rows) == 1
    assert rows[0].id == 1
    assert s1.id == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_seed.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

`grafin_ai_backend/seed.py`:
```python
import asyncio
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from grafin_ai_backend.db import _maker
from grafin_ai_backend.repositories.users import UserRepository
from grafin_ai_backend.schema import SimState
from grafin_ai_backend.security.passwords import hash_password


async def ensure_admin(session: AsyncSession, email: str, password: str):
    repo = UserRepository(session)
    existing = await repo.get_by_email(email)
    if existing is not None:
        return existing
    return await repo.create(
        email=email, password_hash=hash_password(password), role="admin",
        created_at=datetime.now(UTC),
    )


async def ensure_sim_state(session: AsyncSession, start: datetime, speed: float) -> SimState:
    existing = await session.get(SimState, 1)
    if existing is not None:
        return existing
    state = SimState(id=1, sim_now=start, speed=speed, running=False)
    session.add(state)
    await session.flush()
    return state


async def _main() -> None:
    async with _maker()() as session:
        await ensure_admin(session, "admin@grafin.local", "admin")
        await ensure_sim_state(
            session, start=datetime(2025, 9, 1, tzinfo=UTC), speed=60.0
        )
        await session.commit()


if __name__ == "__main__":
    asyncio.run(_main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_seed.py -v`
Expected: PASS. Then full suite: `uv run pytest -v` (all green).

- [ ] **Step 5: Lint**

Run: `uv run ruff check grafin_ai_backend/`
Expected: All checks passed (fix any reported issues).

- [ ] **Step 6: Commit**

```bash
git add grafin_ai_backend/seed.py tests/test_seed.py
git commit -m "feat: seed script (bootstrap admin user + sim_state singleton)"
```

---

### Task 12: Regenerate C4 Component + Code docs

**Files:**
- Modify: `grafin-ai-backend/docs/c4/03-component.md`, `docs/c4/04-code.md`

- [ ] **Step 1: Regenerate Code-level C4**

Use the c4-architecture `c4-code` agent against `grafin_ai_backend/` to add the new modules (redis_client, security/*, repositories/*, services/*, api/*, seed) to `docs/c4/04-code.md`.

- [ ] **Step 2: Regenerate Component-level C4**

Use the `c4-component` agent to add the now-implemented **Authentication/RBAC** and **Redis Integration** components (move them from "planned" to "implemented") and update the diagram in `docs/c4/03-component.md`.

- [ ] **Step 3: Commit**

```bash
git add docs/c4/
git commit -m "docs(c4): add auth/RBAC + redis components"
```

---

## Self-Review

**Spec coverage** (against `docs/superpowers/specs/2026-06-22-backend-api-design.md`):
- §1 layering (`api/`→`services/`→`repositories/`→`security/`) → Tasks 5–10. ✅
- §1 Redis (`redis.asyncio`) → Task 2. ✅
- §3 auth endpoints (login/refresh/logout/me), JWT access 15m + refresh 7d, refresh in Redis revocable, Argon2id, `require_role` default-deny → Tasks 3,4,6,7,8,10. ✅
- §7 rate limiting (auth) → Task 9 (limiter built; wired onto a route in Plan 2B alongside the other endpoints, or apply now as a dependency — limiter is ready). ✅
- §8 `/readyz` checks DB **and** Redis → Task 10. ✅
- §10 C4 deliverable → Task 12. ✅
- Plan-2-notes carry-forward: seed `sim_state` row (Task 11) and dependency-override for tests (Task 10 `client` fixture overrides `get_session` + patches `get_redis`) → addressed. ✅
- **Deferred to Plan 2B (view endpoints) / 2C (WS), intentionally:** all `/metrics|/analytics|/geo|/users|/alerts|/sim|/transactions` endpoints, WS relay, PII masking (used by user-profile endpoints), aggregate Redis caching, request-count middleware.

**Placeholder scan:** none — every code step is complete. Empty `__init__.py` files are explicitly shown as intentionally empty.

**Type consistency:** `CurrentUser(id:int, role:str)`, `TokenPair(access_token, refresh_token)`, `AuthService(users, refresh_store, secret, access_ttl_min, refresh_ttl_days)`, `RefreshTokenStore.save/is_valid/revoke(jti,user_id,...)`, `decode_token(token, secret, algorithm)`, `create_access_token(subject, role, secret, ttl_min)`, `UserRepository.get_by_email/get_by_id/create` — all names/signatures are used identically across the tasks that define and consume them. Seeded first user is `id=1` (Integer PK), matching the `"1"` assertions in Tasks 7 and the auth-API flow. `get_current_user`/`require_role`/`get_session`/`get_redis` match the deps defined in Task 8 and consumed in Task 10.
