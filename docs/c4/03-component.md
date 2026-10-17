# C4 Component Level: Backend API Container

**Date:** 2026-06-22
**Container:** Backend API (`garda-ai-backend`)
**Parent diagram:** [`garda-ai-deploy/docs/c4/02-container.md`](../../../garda-ai-deploy/docs/c4/02-container.md)
**Code-level source:** [`docs/c4/04-code.md`](./04-code.md)

---

## Container Context

The **Backend API** container is one of two application containers in the Garda AI AML platform (the other being the Pipeline Worker). It is a FastAPI/asyncpg ASGI service that:

- Owns the PostgreSQL schema and ORM models used by every platform service
- Exposes health and readiness probes consumed by the container orchestrator (Docker Compose / Kubernetes)
- Exposes a Prometheus `/metrics` endpoint scraped by the platform Prometheus instance
- Authenticates users via argon2id + JWT access/refresh token pairs with single-use rotation
- Enforces role-based access control on protected endpoints
- Stores revocable refresh-token JTIs and per-IP login rate-limit counters in Redis
- Serves REST aggregation endpoints for all dashboard views, role-gated and temporally bounded by the data clock (the newest business time ingested)
- Masks PII (entity names, account IDs) in user-risk responses based on caller role
- Caches aggregate query results in Redis, keyed to the current data-clock timestamp
- Provides a WebSocket live-feed relay that fans out scored events from the Redis `garda:events:live` pub/sub channel to authenticated dashboard clients
- Exposes a token-gated ingest write-path (`POST /api/v1/ingest`, Phase 2) that scores a producer's transaction batch via the outbound garda-ai-scoring service, persists it idempotently, and publishes new events to `garda:events:live`

This document zooms into the **components within that container**. All components run in the same Python process — except the outbound call to the separate **garda-ai-scoring** service, which is the container's one synchronous external HTTP dependency (Phase 2).

---

## Component Summary

| Component | Modules | Responsibility |
|---|---|---|
| **Configuration** | `config.py` | Typed, environment-driven settings; singleton access; fail-closed JWT secret validator |
| **Persistence / Schema** | `db.py`, `schema/` (5 files) | Async DB engine + session factory; canonical ORM data model (7 tables) |
| **Observability** | `observability.py` | Isolated Prometheus registry + metrics; structured JSON logging setup |
| **HTTP App** | `main.py` | FastAPI ASGI app; liveness, readiness, and metrics endpoints; mounts all routers |
| **Authentication & RBAC** | `api/auth.py`, `api/deps.py`, `api/schemas.py`, `services/auth.py`, `security/passwords.py`, `security/tokens.py`, `security/refresh_store.py`, `repositories/users.py` | Login, refresh (rotation), logout, me; JWT issuance + validation; role-gated access; revocable refresh tokens; login rate-limiting |
| **Redis Integration** | `redis_client.py`, `security/refresh_store.py`, `api/ratelimit.py` | Async Redis singleton; revocable refresh-JTI store (atomic consume); fixed-window rate limiting |
| **Seed / Bootstrap** | `seed.py` | Idempotent DB seed: default admin user |
| **View / Read API** | `api/metrics.py`, `api/analytics.py`, `api/geo.py`, `api/transactions.py`, `api/users_view.py`, `api/alerts.py`, `api/system.py`, `api/view_schemas.py`, `repositories/metrics.py`, `repositories/analytics.py`, `repositories/geo.py`, `repositories/transactions.py`, `repositories/users_view.py`, `repositories/alerts.py`, `api/deps.py` (`NowDep`) | Server-side aggregation of all dashboard data over `transaction_events` filtered by `event_time <= now`; role-gated; the data clock as the temporal boundary |
| **PII Masking** | `api/masking.py` | Masks entity names and account/payment IDs in user-risk serialization; applied in router layer, not in repositories |
| **Aggregate Caching** | `api/cache.py` | Data-clock-keyed cache-aside over Redis for aggregate endpoints (metrics, analytics, geo); transactions/live and user-risk are uncached |
| **Live WebSocket Relay** | `api/ws.py`, `api/ws_auth.py`, `realtime/channels.py` | Authenticated (`?token=` access JWT) live fan-out; subscribes to `garda:events:live` Redis pub/sub channel and forwards scored events to dashboard clients via a single blocking poll loop |
| **Ingest Route** *(Phase 2)* | `api/ingest.py`, `api/ingest_schemas.py` | Token-gated `POST /api/v1/ingest` write-path: enrich → score → atomic persist → publish new events to `garda:events:live` (commit-then-notify). Idempotent on producer-provided `transaction_id` |
| **Ingest Auth** *(Phase 2)* | `api/ingest_auth.py` | Bearer `GARDA_INGEST_TOKEN` dependency (settings-only, constant-time); separate from the user JWT auth stack |
| **ScoringClient** *(Phase 2)* | `services/scoring_client.py` | Resilient httpx client (pooled `AsyncClient` on `app.state`) calling the separate garda-ai-scoring service's `POST /v1/score`; bounded retries → `ScoringUnavailable`. The backend's one **outbound** HTTP dependency |
| **IngestRepository** *(Phase 2)* | `repositories/ingest.py` | Enrich lookups (`risk_categories`, `bank_names`) + idempotent batch persist (`ON CONFLICT (id) DO NOTHING ... RETURNING`); events for new ids only, alerts for blocked; one transaction |

---

## Component: Configuration

### Overview

- **Name**: Configuration
- **Type**: Library (singleton provider)
- **Technology**: Python 3.12+, pydantic-settings

### Purpose

Provides a single, validated, cached view of all runtime configuration sourced from environment variables (prefix `GARDA_`) and an optional `.env` file. All other components read configuration through this component — none read environment variables directly.

### Software Features

- **Typed settings**: Declares `database_url` (required), `redis_url`, `jwt_secret`, `jwt_algorithm`, `jwt_access_ttl_min`, `jwt_refresh_ttl_days`, `env`, and `log_level` as typed pydantic fields; unknown variables are silently ignored.
- **Fail-closed JWT secret guard**: `_require_strong_jwt_secret_outside_dev` raises `ValueError` at startup if `env != "development"` and `jwt_secret` is the default placeholder or fewer than 32 characters. Prevents accidental deployment with a weak secret.
- **Singleton caching**: `get_settings()` is decorated with `@lru_cache(maxsize=1)`, guaranteeing the settings object is constructed exactly once per process lifetime.
- **`.env` file support**: Reads a `.env` file at startup if present, enabling local development without shell exports.

### Code Elements

- [`config.py`](../../garda_ai_backend/config.py) — `Settings(BaseSettings)` class and `get_settings()` cached factory function

### Public Interface

#### `get_settings() -> Settings`

The only public symbol. Returns the singleton `Settings` instance.

| Field | Type | Default | Source |
|---|---|---|---|
| `database_url` | `str` | required | `GARDA_DATABASE_URL` |
| `env` | `str` | `"development"` | `GARDA_ENV` |
| `log_level` | `str` | `"INFO"` | `GARDA_LOG_LEVEL` |
| `redis_url` | `str` | `"redis://localhost:6379/0"` | `GARDA_REDIS_URL` |
| `jwt_secret` | `str` | `"change-me-in-prod"` | `GARDA_JWT_SECRET` |
| `jwt_algorithm` | `str` | `"HS256"` | `GARDA_JWT_ALGORITHM` |
| `jwt_access_ttl_min` | `int` | `15` | `GARDA_JWT_ACCESS_TTL_MIN` |
| `jwt_refresh_ttl_days` | `int` | `7` | `GARDA_JWT_REFRESH_TTL_DAYS` |
| `model_name` | `str` | `""` | `GARDA_MODEL_NAME` — set → system health reports `model_accuracy_simulated=false` + `model_name` |
| `llm_provider` | `none\|anthropic\|gemini\|ollama` | `none` | `GARDA_LLM_PROVIDER` — explanation narrative source (`none` = rules only) |
| `llm_api_key` | `SecretStr` | `""` | `GARDA_LLM_API_KEY` (never logged) |
| `llm_model` | `str` | provider default | `GARDA_LLM_MODEL` (`claude-sonnet-5-5` / `gemini-2.5-flash` / `llama3.1:8b`) |
| `llm_base_url` | `str` | provider default | `GARDA_LLM_BASE_URL` |
| `llm_timeout_s` | `float` | `20` | `GARDA_LLM_TIMEOUT_S` |

### Dependencies

- **External**: `pydantic-settings` (BaseSettings, SettingsConfigDict), `pydantic` (model_validator)
- **Components used**: none

---

## Component: Persistence / Schema

### Overview

- **Name**: Persistence / Schema
- **Type**: Library (data access layer + schema registry)
- **Technology**: Python 3.12+, SQLAlchemy 2.0 (async), asyncpg

### Purpose

Provides two closely coupled concerns that are deliberately co-located: the **async database session infrastructure** (`db.py`) and the **canonical ORM data model** (`schema/`). They are grouped as one component because the session factory and ORM models are meaningless without each other — consumers always need both to execute queries.

The schema sub-package is the authoritative definition of all seven PostgreSQL tables used by the platform. The Pipeline Worker and any future services depend on the models defined here (or on the SQL schema that `Base.metadata.create_all()` produces).

### Software Features

- **Async engine with connection pooling**: Creates an `asyncpg`-backed SQLAlchemy engine with `pool_size=10`, `max_overflow=5`, and `pool_pre_ping=True` for resilient connection management.
- **Lazy engine initialisation**: The engine and session factory are constructed on first use and cached for the process lifetime, avoiding startup failures if PostgreSQL is not yet reachable at import time.
- **Request-scoped sessions**: `get_session()` is a FastAPI `yield`-dependency that allocates one `AsyncSession` per HTTP request and returns the connection to the pool on exit, even under exception.
- **Declarative ORM base**: All seven table classes inherit from a single `Base(DeclarativeBase)`, ensuring shared metadata and enabling `Base.metadata.create_all()` for schema migration bootstrapping.
- **Reference tables** (`Bank`, `Entity`, `Account`): Master data for institutions, legal entities, and accounts, including ML-assigned `risk_score` / `risk_category` on `Account`.
- **Transaction tables** (`Transaction`, `TransactionEvent`): Core fact tables. `Transaction` is the primary financial transfer record; `TransactionEvent` is the append-only scoring ledger (one row per scoring pass, status transitions: `approved`, `flagged`, `blocked`).
- **Dual timestamps on `TransactionEvent`**: `surfaced_at` (indexed) is the real ingestion time, written at ingest; `event_time` (indexed, NOT NULL) is business time, denormalized from `transactions.event_time` so read queries stay single-table. Keeping both makes detection lag (`surfaced_at - event_time`) directly measurable, and gives the read layer a business-time column to window and bucket on. `event_time` was introduced by migration `d3c7e1f5a204_add_event_time_to_events` (revises `b2f1a9c4d7e0`), which adds it nullable, backfills from the parent transaction, sets NOT NULL, then creates `ix_transaction_events_event_time`.
- **Alert table** (`Alert`): Human-facing alerts raised from flagged scoring events; tracks analyst acknowledgement workflow (`acknowledged_by`, `acknowledged_at`).
- **User table** (`User`): Platform user accounts (analysts and admins) with Argon2id-hashed credentials and RBAC role field.

### Code Elements

- [`db.py`](../../garda_ai_backend/db.py) — `build_engine()`, `_maker()`, `get_session()`
- [`schema/base.py`](../../garda_ai_backend/schema/base.py) — `Base(DeclarativeBase)`
- [`schema/reference.py`](../../garda_ai_backend/schema/reference.py) — `Bank`, `Entity`, `Account`
- [`schema/transactions.py`](../../garda_ai_backend/schema/transactions.py) — `Transaction`, `TransactionEvent`
- [`schema/alerts.py`](../../garda_ai_backend/schema/alerts.py) — `Alert`
- [`schema/users.py`](../../garda_ai_backend/schema/users.py) — `User`
- [`schema/__init__.py`](../../garda_ai_backend/schema/__init__.py) — re-exports all ORM classes under `garda_ai_backend.schema`

### Public Interface

#### `get_session() -> AsyncIterator[AsyncSession]`

FastAPI dependency. Yields one session per request; auto-closes on completion or exception. Intended usage:

```python
Annotated[AsyncSession, Depends(get_session)]
```

#### `build_engine(url: str) -> AsyncEngine`

Constructs a configured async engine from a connection URL. Exposed for use by testing or migration tooling that needs direct engine access.

#### ORM models (via `garda_ai_backend.schema`)

All seven model classes are importable from the package root:

```python
from garda_ai_backend.schema import (
    Base, Bank, Entity, Account,
    Transaction, TransactionEvent,
    Alert, User,
)
```

`Base.metadata` carries the full DDL and is used by Alembic (or `create_all`) to materialise the schema.

### Dependencies

- **Configuration component**: calls `get_settings()` to obtain `database_url` on first engine construction
- **External — PostgreSQL**: connects via `asyncpg` driver (`postgresql+asyncpg://` URL); pool size 10 + overflow 5

---

## Component: Observability

### Overview

- **Name**: Observability
- **Type**: Library (cross-cutting concern)
- **Technology**: Python 3.12+, prometheus-client, structlog

### Purpose

Provides the two pillars of runtime observability for the Backend API container: **metrics collection** via an isolated Prometheus registry, and **structured logging** via JSON-formatted `structlog` output. Both are configured at import time of `main.py`, before the ASGI server begins accepting requests.

### Software Features

- **Isolated Prometheus registry**: `REGISTRY = CollectorRegistry()` avoids polluting the default process-global registry, preventing conflicts when running alongside other libraries or test frameworks that also register metrics.
- **HTTP request counter**: `REQUEST_COUNT` (`garda_http_requests_total`) is a labelled Counter with dimensions `method`, `path`, `status`. Defined and ready for instrumentation — not yet incremented (middleware/route instrumentation is a planned next step).
- **Structured JSON logging**: `configure_logging(level)` chains three structlog processors — `add_log_level`, `TimeStamper(fmt="iso")`, `JSONRenderer` — producing machine-parseable JSON log lines compatible with log aggregation pipelines (e.g., Loki, Datadog, Cloud Logging).
- **Log level propagation**: Sets the minimum level on both stdlib `logging` and the structlog bound logger, so third-party libraries that use stdlib logging also respect the configured threshold.

### Code Elements

- [`observability.py`](../../garda_ai_backend/observability.py) — `REGISTRY`, `REQUEST_COUNT`, `configure_logging()`

### Public Interface

#### `REGISTRY: CollectorRegistry`

The isolated Prometheus registry. The HTTP App component passes this to `generate_latest()` to serve the `/metrics` endpoint. Future middleware or route handlers should register additional collectors against this registry.

#### `REQUEST_COUNT: Counter`

Pre-defined counter metric. Labels: `method`, `path`, `status`. Currently defined but not yet incremented anywhere in the codebase.

#### `configure_logging(level: str = "INFO") -> None`

Configures stdlib `logging` and `structlog` with structured JSON processors. Called once at process startup from `main.py`.

### Dependencies

- **External**: `prometheus-client` (CollectorRegistry, Counter), `structlog`, `logging`
- **Components used**: none

---

## Component: HTTP App

### Overview

- **Name**: HTTP App
- **Type**: Application (ASGI service entry-point)
- **Technology**: Python 3.12+, FastAPI

### Purpose

The ASGI entry-point for the Backend API container. Creates and owns the `FastAPI` application instance, wires together all components at startup, and mounts all implemented routers. Exposes infrastructure endpoints (liveness, readiness, Prometheus scrape) directly; delegates all API routes to their respective component routers.

### Software Features

- **Import-time initialisation**: Calls `get_settings()` and `configure_logging()` as module-level side effects, ensuring logging is active before any request arrives and before the ASGI server calls any lifecycle hook.
- **Router mounting**: Includes all component routers — `auth`, `metrics`, `analytics`, `geo`, `transactions`, `users_view`, `alerts`, `system`, `ws`, `ingest` — so all API and WebSocket endpoints are served by this process.
- **Liveness probe (`GET /healthz`)**: Returns `{"status": "ok"}` unconditionally. Does not touch the database; safe to call before PostgreSQL is available.
- **Readiness probe (`GET /readyz`)**: Executes `SELECT 1` against PostgreSQL and `PING` against Redis. Returns HTTP 200 `{"status": "ready"}` on success, or HTTP 503 `{"status": "not-ready"}` on any exception.
- **Metrics endpoint (`GET /metrics`)**: Serialises the Observability component's `REGISTRY` via `prometheus_client.generate_latest()` and returns the Prometheus text exposition format with the correct `Content-Type`.

### Code Elements

- [`main.py`](../../garda_ai_backend/main.py) — `app: FastAPI`, `healthz()`, `readyz()`, `metrics()`

### Public Interface

#### HTTP endpoints

| Method | Path | Description | Response |
|---|---|---|---|
| `GET` | `/healthz` | Liveness probe | `200 {"status": "ok"}` |
| `GET` | `/readyz` | Readiness probe (DB + Redis ping) | `200 {"status": "ready"}` or `503 {"status": "not-ready"}` |
| `GET` | `/metrics` | Prometheus scrape | `200` Prometheus text format |
| — | `/api/v1/auth/*` | Auth endpoints (delegated) | See Authentication & RBAC component |
| — | `/api/v1/metrics/*` | Metrics aggregation (delegated) | See View / Read API component |
| — | `/api/v1/analytics/*` | Analytics aggregation (delegated) | See View / Read API component |
| — | `/api/v1/geo/*` | Geo aggregation (delegated) | See View / Read API component |
| — | `/api/v1/transactions/*` | Transaction views (delegated) | See View / Read API component |
| — | `/api/v1/users/*` | User risk views (delegated) | See View / Read API component |
| — | `/api/v1/alerts/*` | Alert views (delegated) | See View / Read API component |
| — | `/api/v1/system/*` | System health (delegated) | See View / Read API component |
| — | `/api/v1/ws/*` | WebSocket live feed (delegated) | See Live WebSocket Relay component |

### Dependencies

- **Configuration component**: `get_settings()` read at import time to obtain `log_level`
- **Persistence / Schema component**: `_maker()` called inside `GET /readyz` to open an ad-hoc database session
- **Observability component**: `configure_logging()` called at import time; `REGISTRY` passed to `generate_latest()` in `GET /metrics`
- **Authentication & RBAC component**: auth `router` included via `app.include_router()`
- **View / Read API component**: all seven view routers included via `app.include_router()`
- **Live WebSocket Relay component**: ws `router` included via `app.include_router()`
- **Redis Integration component**: `get_redis()` called inside `GET /readyz` to ping Redis
- **External — Prometheus**: scrapes `GET /metrics` on the configured interval

---

## Component: Authentication & RBAC

### Overview

- **Name**: Authentication & RBAC
- **Type**: Application (auth layer)
- **Technology**: Python 3.12+, FastAPI, PyJWT, argon2-cffi, pydantic

### Purpose

Implements the complete authentication and authorisation lifecycle for the platform. Handles credential verification (Argon2id), JWT access/refresh token issuance, single-use refresh token rotation, token revocation on logout, identity injection into request handlers, and role-based access control gating. Login attempts are rate-limited per source IP. The `require_role` and `CurrentUserDep` factories defined here are also consumed by the View / Read API component to gate dashboard endpoints. The `decode_token` primitive from `security/tokens.py` is additionally consumed by the Live WebSocket Relay component for query-parameter token authentication.

This component spans the HTTP router layer (`api/`), the service layer (`services/`), the security primitives (`security/`), and the data access layer (`repositories/`) — all tightly coupled around the single concern of auth.

### Software Features

- **Login (`POST /api/v1/auth/login`)**: Accepts email + password, verifies credentials via Argon2id, issues a fresh access + refresh token pair. Rate-limited to 10 requests / 60 s per source IP.
- **Timing equalization**: `dummy_verify()` runs a full Argon2id verification cycle when the email is not found, preventing user enumeration via response latency differences.
- **Token issuance**: Access tokens (15 min TTL, HS256) carry `sub`, `role`, `type="access"`. Refresh tokens (7-day TTL) carry `sub`, `type="refresh"`, and a UUID `jti` used as the Redis store key.
- **Refresh token rotation (`POST /api/v1/auth/refresh`)**: Decodes the refresh token, atomically consumes the JTI from Redis (`GETDEL`), fetches the user, and issues a new token pair. Prevents replay attacks — a JTI can only be spent once.
- **Logout (`POST /api/v1/auth/logout`)**: Revokes the refresh JTI from Redis (best-effort; silently ignores invalid tokens). Returns HTTP 204.
- **Identity probe (`GET /api/v1/auth/me`)**: Requires a valid Bearer access token; returns `{id, email, role}` from a fresh DB lookup.
- **FastAPI dependency injection**: `CurrentUserDep` extracts and validates the Bearer token on every protected route, raising HTTP 401 on failure. `require_role(*roles)` factory raises HTTP 403 if the authenticated user's role is not in the permitted set.
- **Pydantic request/response models**: `LoginRequest`, `RefreshRequest`, `TokenResponse`, `MeResponse` enforce input validation and output shape.

### Code Elements

- [`api/auth.py`](../../garda_ai_backend/api/auth.py) — `router`; routes: `POST /login`, `POST /refresh`, `POST /logout`, `GET /me`
- [`api/deps.py`](../../garda_ai_backend/api/deps.py) — `CurrentUser`, `get_current_user`, `require_role`, `get_auth_service`, `get_data_now`, `NowDep`; type aliases: `SessionDep`, `RedisDep`, `SettingsDep`, `AuthServiceDep`, `CurrentUserDep`
- [`api/schemas.py`](../../garda_ai_backend/api/schemas.py) — `LoginRequest`, `RefreshRequest`, `TokenResponse`, `MeResponse`
- [`services/auth.py`](../../garda_ai_backend/services/auth.py) — `AuthService`, `TokenPair`, `AuthError`
- [`security/passwords.py`](../../garda_ai_backend/security/passwords.py) — `hash_password`, `verify_password`, `dummy_verify`
- [`security/tokens.py`](../../garda_ai_backend/security/tokens.py) — `create_access_token`, `create_refresh_token`, `decode_token`, `InvalidToken`
- [`security/refresh_store.py`](../../garda_ai_backend/security/refresh_store.py) — `RefreshTokenStore` (save, is_valid, consume, revoke)
- [`repositories/users.py`](../../garda_ai_backend/repositories/users.py) — `UserRepository` (get_by_email, get_by_id, create)

### Public Interface

#### HTTP endpoints (mounted at `/api/v1/auth`)

| Method | Path | Auth required | Description | Response |
|---|---|---|---|---|
| `POST` | `/api/v1/auth/login` | No | Credential verification; issues token pair | `200 TokenResponse` or `401` |
| `POST` | `/api/v1/auth/refresh` | No (refresh token in body) | Single-use token rotation | `200 TokenResponse` or `401` |
| `POST` | `/api/v1/auth/logout` | No (refresh token in body) | Revoke refresh JTI | `204` |
| `GET` | `/api/v1/auth/me` | Bearer access token | Return current user identity | `200 MeResponse` or `401/404` |

#### FastAPI dependency injection points

| Symbol | Usage |
|---|---|
| `CurrentUserDep` | Inject authenticated `CurrentUser(id, role)` into any route |
| `require_role("admin")` | Wrap `CurrentUserDep`; raises HTTP 403 if role not permitted |
| `AuthServiceDep` | Inject a fully wired `AuthService` |
| `NowDep` | Inject the data clock — `max(transaction_events.event_time)`, or wall-clock `now()` when the table is empty |

Token expiry deliberately does **not** use `NowDep`: `security/tokens.py` stamps `iat` / `exp` from its own `datetime.now(UTC)`. Minting JWTs against the data clock would date them to 2025 and break login outright.

### Dependencies

- **Persistence / Schema component**: `UserRepository` reads/writes the `users` table via `AsyncSession`; `get_data_now` reads `max(event_time)` from `transaction_events` for `NowDep`
- **Redis Integration component**: `RefreshTokenStore` and `RateLimiter` both consume the Redis client (`RedisDep`)
- **Configuration component**: `get_settings()` provides JWT secret and TTL values

---

## Component: Redis Integration

### Overview

- **Name**: Redis Integration
- **Type**: Library (external-resource adapter)
- **Technology**: Python 3.12+, redis[asyncio]

### Purpose

Provides the async Redis client singleton and the Redis-backed behaviours currently implemented: **revocable refresh-token JTI storage**, **fixed-window per-IP rate limiting**, and **aggregate response caching**. This component acts as the adapter layer between the application and the Redis container provisioned by `garda-ai-deploy`. The Aggregate Caching component (`api/cache.py`) and the Live WebSocket Relay component use the Redis client provided here.

### Software Features

- **Async Redis singleton** (`redis_client.py`): `get_redis()` returns a lazily constructed `redis.asyncio.Redis` client with `decode_responses=True`. URL sourced from `Settings.redis_url`.
- **Refresh JTI store** (`security/refresh_store.py`): `RefreshTokenStore` persists valid refresh-token JTIs at `refresh:{jti}` with TTL matching the JWT expiry. `consume()` uses Redis `GETDEL` for atomic single-use enforcement — two concurrent refresh requests cannot both spend the same token.
- **Fixed-window rate limiter** (`api/ratelimit.py`): `RateLimiter` increments `ratelimit:{key}` via `INCR`, sets TTL on first increment, and raises HTTP 429 when the window limit is exceeded. Currently applied to `POST /api/v1/auth/login` at 10 requests / 60 s per IP.
- **Aggregate cache backing store**: The `agg:{key}` key namespace is used by `api/cache.py` (`cached_json`) to store serialised JSON of aggregate query results. Redis is the storage medium; the caching logic lives in the Aggregate Caching component.
- **Pub/sub transport for live events**: The `redis.asyncio.Redis` client returned by `get_redis()` also provides the `pubsub()` interface consumed by the Live WebSocket Relay to subscribe to `garda:events:live`.

### Code Elements

- [`redis_client.py`](../../garda_ai_backend/redis_client.py) — `build_redis()`, `get_redis()`
- [`security/refresh_store.py`](../../garda_ai_backend/security/refresh_store.py) — `RefreshTokenStore` (shared with Authentication & RBAC component)
- [`api/ratelimit.py`](../../garda_ai_backend/api/ratelimit.py) — `RateLimiter`

### Public Interface

#### `get_redis() -> Redis`

Lazy singleton accessor. Returns the shared `redis.asyncio.Redis` client. Used as the source of the `RedisDep` FastAPI dependency injected into `AuthService`, `RateLimiter`, `cached_json`, and the Live WebSocket Relay.

#### `RefreshTokenStore`

| Method | Signature | Description |
|---|---|---|
| `save` | `(jti, user_id, ttl_seconds) -> None` | Store JTI with TTL |
| `is_valid` | `(jti, user_id) -> bool` | Non-consuming existence check |
| `consume` | `(jti, user_id) -> bool` | Atomic fetch-and-delete (GETDEL) |
| `revoke` | `(jti) -> None` | Unconditional delete (logout) |

#### `RateLimiter`

| Method | Signature | Description |
|---|---|---|
| `check` | `(key: str) -> None` | Increment counter; raise HTTP 429 if over limit |

### Dependencies

- **Configuration component**: `get_settings().redis_url` consumed on first `get_redis()` call
- **External — Redis**: connects via `redis.asyncio.Redis`; uses `SET`, `GET`, `DEL`, `GETDEL`, `INCR`, `EXPIRE`, `PING`, `SUBSCRIBE` (pub/sub)

---

## Component: Seed / Bootstrap

### Overview

- **Name**: Seed / Bootstrap
- **Type**: Utility (run-once CLI tool)
- **Technology**: Python 3.12+

### Purpose

Provides idempotent database seeding functions for bootstrapping the platform. Ensures a default admin user exists in PostgreSQL before the service begins operating. Designed to be run at deploy time or during local development setup; safe to run repeatedly without duplicating data.

There is no clock to seed. "Now" is derived from the ingested data (`max(transaction_events.event_time)`), so a freshly seeded database simply has no timeline yet and the dashboard renders empty until the first batch arrives.

### Software Features

- **Idempotent admin creation** (`ensure_admin`): Checks for an existing user by email; creates one with role `"admin"` and an Argon2id-hashed password only if absent. Returns the existing or newly created `User`.
- **CLI entry point** (`_main`): Seeds `admin@garda.local` with password `"admin"` and commits. Invoked via `python -m garda_ai_backend.seed`.

### Code Elements

- [`seed.py`](../../garda_ai_backend/seed.py) — `ensure_admin()`, `_main()`

### Public Interface

#### `ensure_admin(session, email, password) -> User`

Creates the admin user if absent.

### Dependencies

- **Persistence / Schema component**: `_maker()` for session; `User` ORM model
- **Authentication & RBAC component**: `hash_password()` from `security/passwords.py`

---

## Component: View / Read API

### Overview

- **Name**: View / Read API
- **Type**: Application (dashboard read layer)
- **Technology**: Python 3.12+, FastAPI, SQLAlchemy 2.0 (async), pydantic

### Purpose

Serves all dashboard read endpoints for the Garda AI AML platform. Every endpoint aggregates `transaction_events` rows filtered to `event_time <= now`, where `now` is the data clock injected via the shared `NowDep` dependency. The platform replays a historical AML dataset (IBM HI-Small, spanning `2025-09-01`..`2025-09-10`), so "now" is read out of the data itself — `max(transaction_events.event_time)`, the newest business time ingested — rather than from the wall clock, which would leave every window empty. This temporal boundary is the single point that makes all dashboard panels agree with each other.

All endpoints require an authenticated caller (`CurrentUserDep`). Aggregate results for metrics, analytics, and geo are cached in Redis keyed by that data-clock value, to avoid repeated heavy queries while the clock has not moved. Transaction live-feed and user-risk endpoints are uncached because their result sets change with cursor/filter parameters.

The component is composed of seven FastAPI routers and six query repositories. Response shapes are declared in the shared `view_schemas.py` module.

### Endpoint Groups

| Router prefix | File | Endpoints | Cached |
|---|---|---|---|
| `/api/v1/metrics` | `api/metrics.py` | `GET /overview`, `GET /volume`, `GET /heatmap` | Yes (TTL 5 s) |
| `/api/v1/analytics` | `api/analytics.py` | `GET /fraud` | Yes (TTL 5 s) |
| `/api/v1/geo` | `api/geo.py` | `GET /provinces` | Yes (TTL 10 s) |
| `/api/v1/transactions` | `api/transactions.py` | `GET /live`, `GET /{transaction_id}`, `GET /{transaction_id}/explanation` | Explanation only (`expl:{id}`, 24h) |
| `/api/v1/users` | `api/users_view.py` | `GET /risk`, `GET /{entity_id}/profile` | No |
| `/api/v1/alerts` | `api/alerts.py` | `GET /` (list), `POST /{alert_id}/ack` | No |
| `/api/v1/system` | `api/system.py` | `GET /health` | No |

### Software Features

- **Temporal boundary via `NowDep`**: All view queries receive `now` from a single shared dependency (`get_data_now` in `api/deps.py`) that returns `max(TransactionEvent.event_time)`, falling back to wall-clock `datetime.now(UTC)` only when the table is empty — so a fresh install shows an empty dashboard instead of erroring. All repositories apply `WHERE event_time <= now` to their core fact queries; `UserRiskRepository` applies it as an outer-join condition instead, so entities with no visible events still appear with zero counts.
- **Business time vs. ingestion time**: The views window and bucket exclusively on `event_time` (business time, denormalized onto the event row so these queries stay single-table). `surfaced_at` remains the real ingestion timestamp and is never a window bound or a bucket key; it survives as a value written at ingest and as a field on the live-feed payload, which is what makes detection lag (`surfaced_at - event_time`) measurable.
- **Metrics aggregations** (`api/metrics.py`, `repositories/metrics.py`): Overview (total count, flagged, blocked, total amount, fraud rate), volume time-series (hour / day / month granularity for 24h / weekly / monthly / yearly windows), and 7×24 activity heatmap. All backed by `MetricsRepository`.
- **Fraud analytics** (`api/analytics.py`, `repositories/analytics.py`): Typology distribution (count + amount per typology), and confusion-matrix-derived detection metrics (precision, recall, F1) computed from `is_laundering` ground truth vs. `status` prediction. Backed by `AnalyticsRepository`.
- **Geo distribution** (`api/geo.py`, `repositories/geo.py`): Province-level fraud counts (flagged + blocked events joined through account → entity → province). Risk level derived by count thresholds (≥100: high, ≥20: medium, else low). Backed by `GeoRepository`.
- **Transaction live-feed** (`api/transactions.py`, `repositories/transactions.py`): Cursor-paginated live window (`after_seq` / `limit`) and single-transaction detail endpoint. `TransactionsRepository` joins `transaction_events` → `transactions` → `banks`. Clients use this endpoint to backfill any missed events (e.g., after a WebSocket reconnect). Each row carries exactly the key set the WebSocket relay pushes — `seq`, `transaction_id`, `bank`, `type`, `amount`, `fraud_score`, `typology`, `status`, `surfaced_at`, `event_time` — a deliberate contract so the dashboard's live list and its reconnect-backfill agree field-for-field.
- **User risk profiles** (`api/users_view.py`, `repositories/users_view.py`): Risk-list endpoint (optional `risk` category filter, `limit`) and per-entity profile. `UserRiskRepository` joins entities → accounts → transactions → events. PII (entity name) masked in the router layer via `mask_name` (see PII Masking component); admin callers with `unmasked=true` receive plaintext.
- **Alert management** (`api/alerts.py`, `repositories/alerts.py`): Alert list (all or active-only) and acknowledgement mutation (`POST /{alert_id}/ack`). `AlertsRepository` reads and writes the `alerts` table.
- **System health** (`api/system.py`): Authenticated health endpoint (`GET /api/v1/system/health`) checking DB connectivity, Redis connectivity, and the total count of `transaction_events` rows. That count is deliberately unfiltered — it is an operational "how much is in the database" probe, not a windowed view, so it does not apply the data clock.
- **View schemas** (`api/view_schemas.py`): Pydantic models for all request and response shapes: `MetricsOverviewResponse`, `VolumeResponse`, `HeatmapResponse`, `FraudAnalyticsResponse`, `GeoResponse`, `LiveResponse`, `TransactionDetail`, `UserRiskResponse`, `AlertsResponse`, `SystemHealthResponse`.

### Code Elements

**Routers**
- [`api/metrics.py`](../../garda_ai_backend/api/metrics.py) — `router`; `GET /overview`, `GET /volume`, `GET /heatmap`
- [`api/analytics.py`](../../garda_ai_backend/api/analytics.py) — `router`; `GET /fraud`
- [`api/geo.py`](../../garda_ai_backend/api/geo.py) — `router`; `GET /provinces`
- [`api/transactions.py`](../../garda_ai_backend/api/transactions.py) — `router`; `GET /live`, `GET /{transaction_id}`
- [`api/users_view.py`](../../garda_ai_backend/api/users_view.py) — `router`; `GET /risk`, `GET /{entity_id}/profile`
- [`api/alerts.py`](../../garda_ai_backend/api/alerts.py) — `router`; `GET /`, `POST /{alert_id}/ack`
- [`api/system.py`](../../garda_ai_backend/api/system.py) — `router`; `GET /health`

**Repositories**
- [`repositories/metrics.py`](../../garda_ai_backend/repositories/metrics.py) — `MetricsRepository` (overview, volume, heatmap)
- [`repositories/analytics.py`](../../garda_ai_backend/repositories/analytics.py) — `AnalyticsRepository` (typology_distribution, confusion_counts)
- [`repositories/geo.py`](../../garda_ai_backend/repositories/geo.py) — `GeoRepository` (province_fraud_counts)
- [`repositories/transactions.py`](../../garda_ai_backend/repositories/transactions.py) — `TransactionsRepository` (live_window, detail)
- [`repositories/users_view.py`](../../garda_ai_backend/repositories/users_view.py) — `UserRiskRepository` (risk_list, profile)
- [`repositories/alerts.py`](../../garda_ai_backend/repositories/alerts.py) — `AlertsRepository` (list_alerts, acknowledge)

**Shared**
- [`api/view_schemas.py`](../../garda_ai_backend/api/view_schemas.py) — all Pydantic request/response models for view endpoints
- [`api/deps.py`](../../garda_ai_backend/api/deps.py) — `NowDep`, `CurrentUserDep`, `require_role` (shared with Authentication & RBAC)

### Public Interface

#### HTTP endpoints

| Method | Path | Auth | Description | Response |
|---|---|---|---|---|
| `GET` | `/api/v1/metrics/overview` | Any authenticated | Total transactions, flagged, blocked, amount, fraud rate | `200 MetricsOverviewResponse` |
| `GET` | `/api/v1/metrics/volume` | Any authenticated | Time-series volume (`range` query: 24h/weekly/monthly/yearly) | `200 VolumeResponse` |
| `GET` | `/api/v1/metrics/heatmap` | Any authenticated | 7×24 activity heatmap | `200 HeatmapResponse` |
| `GET` | `/api/v1/analytics/fraud` | Any authenticated | Typology distribution + detection metrics (precision/recall/F1) | `200 FraudAnalyticsResponse` |
| `GET` | `/api/v1/geo/provinces` | Any authenticated | Province-level fraud counts with risk levels | `200 GeoResponse` |
| `GET` | `/api/v1/transactions/live` | Any authenticated | Cursor-paginated live event feed (`after_seq`, `limit`) — also the backfill endpoint for WebSocket clients after a reconnect | `200 LiveResponse` |
| `GET` | `/api/v1/transactions/{id}` | Any authenticated | Single transaction detail with both parties (entity names masked unless admin + `?unmasked=true`); never includes `is_laundering` | `200 TransactionDetail` or `404` |
| `GET` | `/api/v1/transactions/{id}/explanation` | Any authenticated | Evidence (24h point-in-time window), rule-based risk factors and an Indonesian narrative (LLM or deterministic rules fallback); cached in Redis `expl:{id}` | `200 TransactionExplanation` or `404` |
| `GET` | `/api/v1/users/risk` | Any authenticated | Entity risk list (`risk`, `unmasked`, `limit`) | `200 UserRiskResponse` |
| `GET` | `/api/v1/users/{entity_id}/profile` | Any authenticated | Single entity risk profile | `200 RiskProfile` or `404` |
| `GET` | `/api/v1/alerts` | Any authenticated | Alert list (`status=all\|active`) | `200 AlertsResponse` |
| `POST` | `/api/v1/alerts/{id}/ack` | Any authenticated | Acknowledge an alert | `200 AlertItem` or `404` |
| `GET` | `/api/v1/system/health` | Any authenticated | DB + Redis health + total event count | `200 SystemHealthResponse` |

### Dependencies

- **Persistence / Schema component**: all six repositories use `AsyncSession`; ORM models `TransactionEvent`, `Transaction`, `Bank`, `Entity`, `Account`, `Alert`
- **Authentication & RBAC component**: `CurrentUserDep`, `require_role` from `api/deps.py`; `NowDep` also lives in `api/deps.py`
- **Aggregate Caching component**: `cached_json` used by metrics, analytics, and geo routers
- **PII Masking component**: `mask_name` called in `api/users_view.py` before serializing `RiskProfile`
- **Redis Integration component**: `RedisDep` injected into cached endpoints to pass to `cached_json`

---

## Component: PII Masking

### Overview

- **Name**: PII Masking
- **Type**: Library (data sanitisation utility)
- **Technology**: Python 3.12+

### Purpose

Provides pure functions for masking personally identifiable information before it is returned to API callers. Applied in the router layer (not in repositories), ensuring that PII sanitisation is a presentation-layer concern that can be bypassed by privileged callers (`unmasked=true` + admin role) without changing the underlying query logic.

Currently applied exclusively in `api/users_view.py` during `RiskProfile` serialization.

### Software Features

- **Name masking** (`mask_name`): Masks each word of an entity name to its initial character followed by four asterisks. Example: `"Ahmad Setiawan"` → `"A**** S****"`.
- **Account ID masking** (`mask_account_id`): Retains the last four characters of an account or payment ID; masks all preceding characters with `*`. IDs of four or fewer characters are fully masked.
- **Payment ID masking** (`mask_payment_id`): Delegates to `mask_account_id` — same masking rule applied to payment reference strings.

### Code Elements

- [`api/masking.py`](../../garda_ai_backend/api/masking.py) — `mask_name`, `mask_account_id`, `mask_payment_id`

### Public Interface

| Function | Signature | Description |
|---|---|---|
| `mask_name` | `(name: str) -> str` | Mask each word to initial + `****` |
| `mask_account_id` | `(account_id: str) -> str` | Keep last 4 chars; mask the rest |
| `mask_payment_id` | `(payment_id: str) -> str` | Alias of `mask_account_id` |

### Dependencies

- **External**: none (pure Python)
- **Components used**: none (consumed by View / Read API)

---

## Component: Aggregate Caching

### Overview

- **Name**: Aggregate Caching
- **Type**: Library (cache-aside decorator)
- **Technology**: Python 3.12+, redis[asyncio]

### Purpose

Provides a single `cached_json` helper that implements a cache-aside pattern over Redis for aggregate query results. Results are serialised to JSON, stored under the `agg:{key}` namespace with a configurable TTL, and returned directly on subsequent requests with the same key. The cache key is always constructed to include `now.isoformat()`, so cached results are automatically superseded when the data clock advances.

Applied to the three heaviest aggregate endpoint groups: metrics (TTL 5 s), analytics (TTL 5 s), and geo (TTL 10 s). Transaction live-feed endpoints and user-risk endpoints are explicitly not cached because their result sets are parametrised by cursor/filter arguments that make key construction impractical without per-request granularity.

### Software Features

- **Cache-aside read-through** (`cached_json`): Checks `agg:{key}` in Redis. On a hit, deserialises and returns the cached value. On a miss, calls the async `compute` callable, serialises the result via `json.dumps(..., default=str)`, stores it with the given TTL, and returns the fresh value.
- **Data-clock-keyed cache invalidation**: Callers include `now.isoformat()` in the key (e.g., `f"overview:{now.isoformat()}"`), so a new key appears as soon as the data clock advances — that is, as soon as an event with a newer `event_time` is ingested — and the stale entry simply expires by TTL. The mechanism is unchanged from the earlier design; what the key tracks is not.
- **`default=str` serialisation**: Handles non-JSON-native types (notably `datetime` objects returned by SQLAlchemy) without requiring callers to pre-serialise their results.

### Code Elements

- [`api/cache.py`](../../garda_ai_backend/api/cache.py) — `cached_json`

### Public Interface

#### `cached_json(redis, key, ttl, compute) -> Any`

| Parameter | Type | Description |
|---|---|---|
| `redis` | `Redis` | Async Redis client (from `RedisDep`) |
| `key` | `str` | Cache key suffix; stored as `agg:{key}` |
| `ttl` | `int` | Seconds until the cached entry expires |
| `compute` | `Callable[[], Awaitable[Any]]` | Async factory called on a cache miss |

Returns the cached or freshly computed value.

### Dependencies

- **Redis Integration component**: `redis.asyncio.Redis` client passed in by caller
- **External**: `redis[asyncio]`, `json`
- **Components used**: none (consumed by View / Read API)

---

## Component: Live WebSocket Relay

### Overview

- **Name**: Live WebSocket Relay
- **Type**: Application (real-time push layer)
- **Technology**: Python 3.12+, FastAPI WebSockets, redis[asyncio] pub/sub

### Purpose

Provides authenticated, real-time push of scored AML events to dashboard clients over a persistent WebSocket connection. The relay subscribes to the Redis `garda:events:live` pub/sub channel — the channel the Plan 3 pipeline worker publishes to after each scoring pass — and forwards each message directly to the connected client in a single blocking poll loop. Backpressure is the natural `send_text` await; there is no in-process queue and no resync sentinel.

Authentication is performed before the WebSocket handshake is accepted: the standard JWT access token is passed as a `?token=` query parameter (Bearer headers are not available in the browser WebSocket API). An invalid or missing token causes an immediate close with code 1008 (Policy Violation) before `accept()` is called.

This is the final backend API surface of Plan 2. The pipeline publisher (the Plan 3 worker that writes to `garda:events:live`) is **not part of this repository** and does not exist yet.

### Software Features

- **Auth-before-accept**: `authenticate_ws_token` validates the `?token=` query parameter using `decode_token` and checks `claims["type"] == "access"`. If validation fails, the WebSocket is closed with code 1008 without being accepted — no handshake is completed for unauthenticated callers.
- **Redis pub/sub subscription**: On successful auth, the handler calls `redis.pubsub()` and subscribes to `LIVE_EVENTS_CHANNEL` (`"garda:events:live"`). The channel name is defined as a shared constant in `realtime/channels.py` to keep the relay and the future pipeline publisher in sync.
- **Connected sentinel**: Immediately after `accept()`, a `{"type": "connected"}` message is sent to confirm the subscription is live before any events arrive.
- **Single-loop poll-and-forward**: The handler enters a `while True` loop calling `pubsub.get_message(ignore_subscribe_messages=True, timeout=15)`. When a `"message"` arrives, `send_text(message["data"])` forwards the raw event JSON to the client immediately. No concurrent reader/writer tasks and no in-process queue — the prior concurrent-task pattern delivered correctly under Starlette's in-process test transport but did not deliver messages under uvicorn's real WebSocket transport, so it was replaced by this single-coroutine design.
- **Natural backpressure**: Because `send_text` is awaited inline, a slow client naturally throttles the poll loop. There is no bounded queue, no drop-to-latest, and no `{"type": "resync"}` sentinel. Clients still recover any gaps by calling `GET /transactions/live?after_seq=<last_seq>` (the consistency contract is unchanged).
- **Disconnect detection**: `send_text` raises `WebSocketDisconnect` when the client goes away, ending the loop. The `finally` block unsubscribes and closes the pub/sub connection best-effort.
- **Integration test coverage**: The relay is verified by `tests/test_ws_uvicorn.py`, which runs a real uvicorn instance in-process to confirm end-to-end delivery — the test that exposed the concurrent-task transport failure.
- **Shared channel constant**: `LIVE_EVENTS_CHANNEL = "garda:events:live"` in `realtime/channels.py` is the single source of truth for the channel name, establishing the cross-repo contract between this relay and the Plan 3 pipeline worker.

### Code Elements

- [`api/ws.py`](../../garda_ai_backend/api/ws.py) — `router`; `WS /api/v1/ws/live`; `_POLL_TIMEOUT = 15.0`; single-loop poll-and-forward handler
- [`api/ws_auth.py`](../../garda_ai_backend/api/ws_auth.py) — `authenticate_ws_token(token, secret) -> CurrentUser | None`
- [`realtime/channels.py`](../../garda_ai_backend/realtime/channels.py) — `LIVE_EVENTS_CHANNEL = "garda:events:live"`

### Public Interface

#### WebSocket endpoint

| Protocol | Path | Auth | Description |
|---|---|---|---|
| `WS` | `/api/v1/ws/live` | `?token=<access_jwt>` | Subscribe to live scored-event stream |

**Connection lifecycle:**

1. Client connects with `?token=<access_jwt>`.
2. Server validates the token; closes 1008 on failure (no accept).
3. Server accepts, subscribes to Redis channel, sends `{"type": "connected"}`.
4. Server polls Redis (`get_message`, timeout 15 s) in a single loop; forwards each event payload as a `send_text` call.
5. On client disconnect (`WebSocketDisconnect` raised by `send_text`), the loop exits and the pub/sub connection is closed best-effort.
6. Clients may call `GET /transactions/live?after_seq=<last_seq>` at any time to backfill missed events.

#### `authenticate_ws_token(token: str, secret: str) -> CurrentUser | None`

| Parameter | Type | Description |
|---|---|---|
| `token` | `str` | Raw JWT string from `?token=` query param |
| `secret` | `str` | HMAC secret from `Settings.jwt_secret` |

Returns a `CurrentUser(id, role)` on success, `None` on any validation failure (missing token, invalid signature, wrong type claim).

#### `LIVE_EVENTS_CHANNEL: str`

`"garda:events:live"` — the Redis pub/sub channel name. Cross-repo contract: the Plan 3 pipeline worker must `PUBLISH` to this channel for the relay to receive events.

### Dependencies

- **Authentication & RBAC component**: `decode_token`, `InvalidToken` from `security/tokens.py`; `CurrentUser`, `RedisDep`, `SettingsDep` from `api/deps.py`
- **Redis Integration component**: `RedisDep` (the async Redis client); uses `pubsub()`, `subscribe()`, `listen()`, `unsubscribe()`, `aclose()`
- **Configuration component**: `SettingsDep` provides `jwt_secret` for token validation
- **External — Redis**: subscribes to `garda:events:live` channel; receives messages published by the pipeline worker
- **External (planned) — Pipeline Worker (Plan 3)**: the external publisher that writes scored `TransactionEvent` records to the DB and publishes event JSON to `garda:events:live`; not yet implemented

---

## Component: Ingest Auth *(Phase 2 — added 2026-06-25)*

### Overview

- **Name**: Ingest Auth
- **Type**: Library (auth dependency)
- **Technology**: Python 3.12+, FastAPI, `hmac`

### Purpose

Gates the ingest write-path with a shared bearer token that is completely separate from the user JWT auth stack. The producer (the pipeline / scoring feeder that calls `POST /api/v1/ingest`) is a machine, not a dashboard user, so it authenticates with a single long-lived secret (`GARDA_INGEST_TOKEN`) rather than a login-issued access token. This keeps the two trust domains — human dashboard users and the trusted event producer — cleanly isolated.

### Software Features

- **Settings-only token**: `require_ingest_token` reads the expected token exclusively from `get_settings().ingest_token`. There is no per-request override path, so a caller cannot influence which token is checked against.
- **Constant-time comparison**: `_verify_ingest` compares the presented value against the configured token with `hmac.compare_digest`, avoiding a timing side-channel on the secret.
- **Bearer scheme enforcement**: The `Authorization` header must be `Bearer <token>`; a missing header, wrong scheme, or mismatched value raises HTTP 401 with a `WWW-Authenticate: Bearer` challenge.
- **Router-level application**: Applied once as a router dependency (`APIRouter(..., dependencies=[Depends(require_ingest_token)])`), so every route mounted under the ingest router is gated uniformly.

### Code Elements

- [`api/ingest_auth.py`](../../garda_ai_backend/api/ingest_auth.py) — `require_ingest_token` (FastAPI dependency), `_verify_ingest` (pure, unit-testable check)

### Public Interface

#### `require_ingest_token(authorization: str | None = Header(default=None)) -> None`

FastAPI dependency. Passes silently on a valid token; raises HTTP 401 otherwise. Mounted on the ingest router so it guards `POST /api/v1/ingest`.

### Dependencies

- **Configuration component**: `get_settings().ingest_token` (required, min length 16)
- **External**: `hmac` (constant-time compare), FastAPI (`Header`, `HTTPException`)

---

## Component: ScoringClient *(Phase 2 — added 2026-06-25)*

### Overview

- **Name**: ScoringClient
- **Type**: Library (external-service adapter)
- **Technology**: Python 3.12+, httpx (async)

### Purpose

Adapter for the backend's single **outbound** HTTP dependency: the separate **garda-ai-scoring** service's `POST /v1/score`. The ingest route delegates all batch scoring to this client. Scoring is now an outbound synchronous dependency of the request path — a failed or unreachable scoring service is a first-class error condition that the ingest route surfaces as HTTP 503 (nothing is persisted).

### Software Features

- **Pooled shared client**: Wraps a single `httpx.AsyncClient` created once at startup and stored on `app.state.http_client` (via the `main.py` lifespan). Connection pooling is reused across requests rather than opening a client per call.
- **Bearer auth**: Sends `Authorization: Bearer <scoring_token>` on every call.
- **Correlation propagation**: Forwards the request's `X-Correlation-ID` to the scoring service so a single ingest can be traced end-to-end across the two services.
- **Bounded retries with backoff**: Retries transient transport errors and 5xx responses up to `retries` times with exponential backoff (0.1s, 0.2s, …); exhausting retries raises `ScoringUnavailable`.
- **4xx is terminal**: A 4xx from scoring is treated as a contract/auth problem and is **not** retried — it raises `ScoringUnavailable` immediately.
- **Response validation**: A malformed success body (missing/!`results`) raises `ScoringUnavailable` rather than returning garbage downstream.

### Code Elements

- [`services/scoring_client.py`](../../garda_ai_backend/services/scoring_client.py) — `ScoringClient` (`score()`), `ScoringUnavailable`

### Public Interface

#### `ScoringClient(client, base_url, token, *, retries=2, timeout_s=5.0)`

#### `async score(transactions: list[dict], correlation_id: str | None = None) -> list[dict]`

POSTs `{"transactions": [...]}` to `<base_url>/v1/score`; returns the `results` list. Raises `ScoringUnavailable` on unreachable service, exhausted retries, any 4xx, or a malformed response.

### Dependencies

- **Configuration component**: `scoring_url`, `scoring_token`, `scoring_timeout_s`, `scoring_retries`
- **HTTP App component**: the pooled `httpx.AsyncClient` on `app.state` (created/closed by the `main.py` lifespan)
- **External — garda-ai-scoring**: `POST /v1/score` (bearer `scoring_token`, `X-Correlation-ID` propagated) — a separate service/container
- **External**: `httpx`, `asyncio`

---

## Component: IngestRepository *(Phase 2 — added 2026-06-25)*

### Overview

- **Name**: IngestRepository
- **Type**: Library (data access layer)
- **Technology**: Python 3.12+, SQLAlchemy 2.0 (async), asyncpg (PostgreSQL dialect `pg_insert`)

### Purpose

Owns all database access for the ingest write-path: reference-data enrichment lookups and the idempotent batch persist. Producer-provided `transaction_id`s are the transaction primary key, so re-ingesting the same batch is a no-op — the repository never double-inserts events or alerts for an already-seen id.

### Software Features

- **Enrichment lookups**: `risk_categories(account_ids)` maps `from_account → risk_category` (fed into the scoring payload); `bank_names(bank_ids)` maps `from_bank_id → name` (fed into the published live-feed message). Missing ids are simply omitted.
- **Idempotent insert**: `persist()` uses `pg_insert(Transaction) ... .on_conflict_do_nothing(index_elements=[Transaction.id]).returning(Transaction.id)`; only the genuinely-new ids are returned, and events are created **only** for those.
- **Events for new ids, alerts for blocked**: Inserts one `TransactionEvent` per newly-inserted transaction (returning `seq`), then one `Alert` per event whose status is `blocked`.
- **Single transaction**: The whole insert sequence runs inside one `async with session.begin()` block, so the batch commits atomically or not at all.
- **Early exit**: If no ids are new (full duplicate batch), returns `[]` without touching the events/alerts tables.

### Code Elements

- [`repositories/ingest.py`](../../garda_ai_backend/repositories/ingest.py) — `IngestRepository` (`risk_categories`, `bank_names`, `persist`), `InsertedEvent` (frozen dataclass: `seq`, `transaction_id`, `fraud_score`, `typology`, `status`)

### Public Interface

| Method | Signature | Description |
|---|---|---|
| `risk_categories` | `(account_ids: list[str]) -> dict[str, str \| None]` | Enrich: account id → risk_category |
| `bank_names` | `(bank_ids: list[str]) -> dict[str, str]` | Enrich: bank id → name |
| `persist` | `(transactions: list[dict], scores_by_id: dict[int, dict], now: datetime) -> list[InsertedEvent]` | Idempotent atomic insert of transactions + events (+ alerts for blocked); returns the newly-inserted events with their `seq` |

### Dependencies

- **Persistence / Schema component**: `AsyncSession`; ORM models `Account`, `Bank`, `Transaction`, `TransactionEvent`, `Alert`
- **External**: SQLAlchemy `select` + PostgreSQL `insert` (`on_conflict_do_nothing`, `returning`)

---

## Component: Ingest Route *(Phase 2 — added 2026-06-25)*

### Overview

- **Name**: Ingest Route
- **Type**: Application (write-path router)
- **Technology**: Python 3.12+, FastAPI, pydantic, structlog

### Purpose

The token-gated write-path that lets a trusted producer push a batch of transactions into the platform. It orchestrates the four Phase 2 components: enrich the batch, score it via the outbound `ScoringClient`, persist it idempotently via `IngestRepository`, and publish each newly-created event to the same Redis `garda:events:live` channel the WebSocket relay and frontend already consume. The published message uses the **same shape** the read/live path emits, so no consumer change is required.

This is an **additive** surface. The Phase 1 label-replay and dashboard read paths are unchanged by this work; re-anchoring the read/aggregate layer onto ingest-produced events is deferred to **Phase 5**.

### Software Features

- **Orchestrated flow**: `enrich (from_risk_category)` → `score batch` → `atomic persist` → `publish each new event`.
- **Fail-fast on scoring**: If `ScoringClient` raises `ScoringUnavailable`, the route returns **503** and nothing is persisted. If scoring returns incomplete/invalid results (missing id, bad status, non-numeric `fraud_score`), it returns **502**.
- **Idempotent**: Idempotent on the producer-provided `transaction_id` (via `IngestRepository.persist`'s `ON CONFLICT DO NOTHING`); duplicates are reported with `ingested=false` and no `seq`.
- **Commit-then-notify**: Redis publishes happen **after** the DB commit. A publish failure leaves events persisted-but-not-published (accepted for Phase 2; a transactional outbox is out of scope).
- **DB-before-scoring connection hygiene**: The enrichment SELECT's autobegun read-only transaction is rolled back before the scoring network round-trip, so a DB connection is not pinned across the outbound HTTP call.
- **Correlation ID**: Honors an inbound `X-Correlation-ID` (or generates one), binds it to the structlog context, and propagates it to the scoring call.
- **Metrics**: Records `garda_ingest_transactions_total{result}` (`inserted` / `duplicate`) and `garda_ingest_scoring_latency_seconds` (observed in a `finally`, so slow/failed scoring calls are captured too).
- **Input caps**: Batch capped at 1000 transactions; per-field length/precision caps via `ingest_schemas`.
- **Error surface**: `200` (success, per-item results) / `400` (FK violation — unknown bank/account, SQLSTATE 23503) / `401` (bad/missing ingest token) / `422` (schema validation) / `502` (invalid scoring results) / `503` (scoring unavailable).

### Code Elements

- [`api/ingest.py`](../../garda_ai_backend/api/ingest.py) — `router` (prefix `/api/v1`, gated by `require_ingest_token`); `ingest()` handler; `get_scoring_client()` (builds a `ScoringClient` around the pooled `app.state.http_client`)
- [`api/ingest_schemas.py`](../../garda_ai_backend/api/ingest_schemas.py) — `IngestTxn`, `IngestRequest`, `IngestResultItem`, `IngestResponse`

### Public Interface

#### HTTP endpoint

| Method | Path | Auth | Description | Response |
|---|---|---|---|---|
| `POST` | `/api/v1/ingest` | Bearer `GARDA_INGEST_TOKEN` | Enrich → score → atomic persist → publish scored batch | `200 IngestResponse` / `400` / `401` / `422` / `502` / `503` |

### Dependencies

- **Ingest Auth component**: `require_ingest_token` gates the router
- **ScoringClient component**: outbound `POST /v1/score` (via the pooled `app.state.http_client`)
- **IngestRepository component**: enrichment + idempotent atomic persist
- **Persistence / Schema component**: `SessionDep`
- **Redis Integration component**: `RedisDep` — `PUBLISH garda:events:live` (commit-then-notify)
- **Observability component**: `INGEST_TRANSACTIONS`, `INGEST_SCORING_LATENCY`
- **Live WebSocket Relay component** *(indirect)*: consumes the published `garda:events:live` messages this route emits (same message shape)

---

## Component Diagram

The diagram below shows all fifteen components within the Backend API container (eleven Phase 1 components plus the four Phase 2 ingest-write-path components), their internal relationships, and their connections to external systems and other containers.

```mermaid
C4Component
    title Component Diagram — Backend API Container (garda-ai-backend)

    Container_Boundary(api, "Backend API · FastAPI / asyncpg / redis-py") {
        Component(httpApp, "HTTP App", "FastAPI", "ASGI entry-point. Liveness (/healthz), readiness (/readyz), Prometheus scrape (/metrics). Mounts all routers including WebSocket relay.")
        Component(config, "Configuration", "pydantic-settings", "Typed, cached settings from GARDA_* env vars. JWT secret + Redis URL. Fail-closed secret validator.")
        Component(persistence, "Persistence / Schema", "SQLAlchemy 2.0 + asyncpg", "Async engine + session factory. Canonical ORM for all 7 tables: banks, entities, accounts, transactions, transaction_events, alerts, users. transaction_events carries both surfaced_at (ingestion time) and event_time (business time).")
        Component(observability, "Observability", "prometheus-client + structlog", "Isolated Prometheus registry + garda_http_requests_total counter. Structured JSON logging.")
        Component(auth, "Authentication & RBAC", "FastAPI + PyJWT + argon2-cffi", "Login/refresh/logout/me. Argon2id password verify. JWT issuance + validation. Single-use refresh rotation. Role-gated DI (require_role / CurrentUserDep / NowDep). Token iat/exp use the wall clock, never the data clock. Login rate-limiting.")
        Component(redis, "Redis Integration", "redis[asyncio]", "Async Redis singleton. Refresh-JTI store (atomic GETDEL). Fixed-window rate limiter (INCR/EXPIRE). Pub/sub client for live event channel.")
        Component(seed, "Seed / Bootstrap", "Python asyncio", "Idempotent DB seed: default admin user. Run at deploy time.")
        Component(viewApi, "View / Read API", "FastAPI + SQLAlchemy", "7 routers + 6 repositories. Aggregates transaction_events WHERE event_time <= now, where now = max(event_time) — the data clock. Endpoints: metrics, analytics, geo, transactions, users, alerts, system. /transactions/live?after_seq= is the backfill endpoint for WS clients after reconnect.")
        Component(masking, "PII Masking", "Python", "mask_name / mask_account_id. Applied in users_view router before RiskProfile serialization. Admin callers with unmasked=true bypass masking.")
        Component(cache, "Aggregate Caching", "redis[asyncio] + json", "cached_json cache-aside over Redis. Data-clock-keyed. Applied to metrics, analytics, geo (TTL 5-10 s). Transactions/live and user-risk are uncached.")
        Component(wsRelay, "Live WebSocket Relay", "FastAPI WebSockets + redis pub/sub", "WS /api/v1/ws/live. Auth-before-accept via ?token= JWT. Single-loop poll-and-forward: subscribe → send connected → get_message(timeout=15) → send_text. No queue; natural send-await backpressure. Clients backfill gaps via GET /transactions/live?after_seq=.")
        Component(ingestRoute, "Ingest Route (Phase 2)", "FastAPI + pydantic", "POST /api/v1/ingest. Token-gated write-path. enrich → score → atomic persist → publish new events to garda:events:live (commit-then-notify). Idempotent on producer transaction_id. 200/400/401/422/502/503.")
        Component(ingestAuth, "Ingest Auth (Phase 2)", "FastAPI + hmac", "require_ingest_token — bearer GARDA_INGEST_TOKEN, settings-only, constant-time. Separate from user JWT auth.")
        Component(scoringClient, "ScoringClient (Phase 2)", "httpx async", "Resilient client for garda-ai-scoring POST /v1/score. Pooled AsyncClient on app.state. Bearer scoring_token, X-Correlation-ID propagated, bounded retries, 4xx-no-retry → ScoringUnavailable.")
        Component(ingestRepo, "IngestRepository (Phase 2)", "SQLAlchemy 2.0 + pg_insert", "Enrich (risk_categories, bank_names) + idempotent batch persist: ON CONFLICT (id) DO NOTHING RETURNING. Events for new ids only, alerts for blocked. One transaction.")
    }

    ContainerDb(pg, "PostgreSQL", "PostgreSQL", "Source of truth for all platform data")
    ContainerDb(redisDb, "Redis", "Redis", "Refresh-JTI store; rate-limit counters; agg:* cache entries; garda:events:live pub/sub channel")
    Container_Ext(prom, "Prometheus", "Prometheus", "Scrapes /metrics from Backend API")
    Container_Ext(worker, "Pipeline Worker (Plan 3)", "Python / asyncpg", "ETL, replay clock, ML scoring engine — reads/writes same DB schema. PUBLISHES scored events to garda:events:live. Not yet implemented.")
    Container_Ext(dashboard, "Dashboard Client", "Browser / WebSocket", "Connects to WS /api/v1/ws/live; backfills via GET /transactions/live?after_seq=")
    Container_Ext(scoringSvc, "garda-ai-scoring (Phase 2)", "Separate service", "Scoring service. Exposes POST /v1/score (bearer). Outbound HTTP dependency of the Ingest Route.")
    Container_Ext(producer, "Ingest Producer (Phase 2)", "Trusted machine client", "Pushes transaction batches to POST /api/v1/ingest with the shared GARDA_INGEST_TOKEN bearer.")

    Rel(httpApp, config, "Reads settings at import time", "in-process")
    Rel(httpApp, persistence, "Opens ad-hoc session for /readyz", "in-process")
    Rel(httpApp, observability, "Configures logging at import time; serves REGISTRY on /metrics", "in-process")
    Rel(httpApp, auth, "Mounts auth router", "in-process")
    Rel(httpApp, viewApi, "Mounts 7 view routers", "in-process")
    Rel(httpApp, redis, "Pings Redis for /readyz", "in-process")
    Rel(httpApp, wsRelay, "Mounts WebSocket router", "in-process")

    Rel(persistence, config, "Reads database_url on first engine construction", "in-process")
    Rel(redis, config, "Reads redis_url on first client construction", "in-process")

    Rel(auth, persistence, "UserRepository reads/writes users table; get_data_now reads max(transaction_events.event_time) for NowDep", "in-process / SQL")
    Rel(auth, redis, "RefreshTokenStore (JTI save/consume/revoke); RateLimiter (login check)", "in-process")
    Rel(auth, config, "Reads JWT secret + TTL settings", "in-process")

    Rel(viewApi, persistence, "6 repositories query transaction_events, transactions, alerts, entities, accounts, banks", "in-process / SQL")
    Rel(viewApi, auth, "Uses CurrentUserDep, require_role, NowDep from api/deps.py", "in-process")
    Rel(viewApi, cache, "metrics, analytics, geo routers call cached_json", "in-process")
    Rel(viewApi, masking, "users_view router calls mask_name for RiskProfile serialization", "in-process")

    Rel(cache, redis, "GET / SET agg:* keys with TTL", "in-process")

    Rel(seed, persistence, "ensure_admin via AsyncSession", "in-process / SQL")
    Rel(seed, auth, "Uses hash_password from security/passwords", "in-process")

    Rel(wsRelay, auth, "authenticate_ws_token uses decode_token + CurrentUser from api/deps.py", "in-process")
    Rel(wsRelay, redis, "redis.pubsub() — SUBSCRIBE garda:events:live", "in-process")
    Rel(wsRelay, config, "Reads jwt_secret via SettingsDep for token validation", "in-process")

    Rel(persistence, pg, "Reads and writes", "SQL / asyncpg (pool: 10+5)")
    Rel(redis, redisDb, "INCR, EXPIRE, SET, GET, DEL, GETDEL, PING, SUBSCRIBE", "redis-py async")
    Rel(cache, redisDb, "GET / SET agg:* (via Redis Integration client)", "redis-py async")
    Rel(wsRelay, redisDb, "SUBSCRIBE garda:events:live — receives published events", "redis-py async pub/sub")
    Rel(prom, httpApp, "Scrapes", "HTTP GET /metrics")
    Rel(worker, pg, "Reads and writes (sole writer of transactions/events)", "SQL / asyncpg")
    Rel(worker, redisDb, "PUBLISH garda:events:live (planned — not yet implemented)", "redis PUBLISH")
    Rel(dashboard, wsRelay, "Connects with ?token=<jwt>; receives live event frames", "WebSocket")
    Rel(dashboard, viewApi, "Backfills via GET /transactions/live?after_seq= after reconnect", "HTTP")

    %% Phase 2 — ingest write-path
    Rel(httpApp, ingestRoute, "Mounts ingest router; owns pooled httpx.AsyncClient via lifespan", "in-process")
    Rel(ingestRoute, ingestAuth, "Router gated by require_ingest_token", "in-process")
    Rel(ingestRoute, scoringClient, "Scores batch (built around app.state.http_client)", "in-process")
    Rel(ingestRoute, ingestRepo, "Enrich + idempotent atomic persist", "in-process / SQL")
    Rel(ingestRoute, redis, "PUBLISH garda:events:live (commit-then-notify)", "in-process")
    Rel(ingestRoute, observability, "garda_ingest_transactions_total / garda_ingest_scoring_latency_seconds", "in-process")
    Rel(ingestAuth, config, "Reads ingest_token", "in-process")
    Rel(scoringClient, config, "Reads scoring_url / scoring_token / timeout / retries", "in-process")
    Rel(ingestRepo, persistence, "accounts, banks, transactions, transaction_events, alerts", "in-process / SQL")
    Rel(producer, ingestRoute, "POST /api/v1/ingest with bearer GARDA_INGEST_TOKEN", "HTTP")
    Rel(scoringClient, scoringSvc, "POST /v1/score (bearer, X-Correlation-ID)", "HTTP outbound")
    Rel(ingestRoute, redisDb, "PUBLISH garda:events:live — fans out to WS relay + dashboard", "redis PUBLISH")
```

---

## Relationship to the Container Diagram

The Container diagram in `garda-ai-deploy/docs/c4/02-container.md` assigns the following responsibilities to the **Backend API** container. The table below maps each responsibility to its implementation status:

| Container-level responsibility | Status | Implementing component |
|---|---|---|
| REST aggregations for every view | **Implemented** | View / Read API |
| WebSocket live-feed relay | **Implemented** | Live WebSocket Relay (`api/ws.py`, `api/ws_auth.py`, `realtime/channels.py`) |
| Auth / RBAC | **Implemented** | Authentication & RBAC |
| PII masking | **Implemented** | PII Masking (applied in View / Read API — users_view router) |
| Aggregate caching | **Implemented** | Aggregate Caching (metrics, analytics, geo; transactions/live and user-risk uncached) |
| Owns DB schema + migrations | **Implemented** | Persistence / Schema |
| Health / readiness probes | **Implemented** | HTTP App |
| Prometheus `/metrics` endpoint | **Implemented** | HTTP App + Observability |
| Connects to PostgreSQL | **Implemented** | Persistence / Schema |
| Connects to Redis | **Implemented** (JTI store + rate limiting + aggregate cache + pub/sub) | Redis Integration + Aggregate Caching + Live WebSocket Relay |
| Login rate-limiting | **Implemented** | Redis Integration (via Authentication & RBAC) |
| Bootstrap / seed | **Implemented** | Seed / Bootstrap |
| Ingest write-path (`POST /api/v1/ingest`) *(Phase 2)* | **Implemented** | Ingest Route + Ingest Auth + ScoringClient + IngestRepository |
| Outbound scoring call *(Phase 2)* | **Implemented** | ScoringClient → garda-ai-scoring `POST /v1/score` |

All eleven Phase 1 components plus the four Phase 2 ingest-write-path components are implemented. The Phase 2 ingest work is **additive**: the label-replay and dashboard read/aggregate paths are unchanged, and re-anchoring the read layer onto ingest-produced events is deferred to **Phase 5**. The **Pipeline Worker (Plan 3)** is no longer the only way events reach `garda:events:live` — the Ingest Route now publishes there too — but it remains a separate repository and is out of scope here.

---

## Changelog

| Date | Change |
|---|---|
| 2026-08-12 | **Simulation clock removed; read layer re-anchored on the data clock.** The simulation-control subsystem is deleted outright — its router, repository, ORM model, request/response schemas, and both `/api/v1/sim` endpoints are gone, and its singleton control table was dropped by migration `b2f1a9c4d7e0`. The ORM is now 7 tables and the View / Read API is 7 routers + 6 repositories. `api/deps.py` replaces the old clock dependency with `get_data_now` / `NowDep`, which returns `max(transaction_events.event_time)` — the newest business time ingested — and falls back to wall-clock `now()` only on an empty table; it no longer 404s on uninitialised state. `transaction_events` gained `event_time` (TIMESTAMPTZ, NOT NULL, indexed) via migration `d3c7e1f5a204_add_event_time_to_events`, denormalized from `transactions.event_time` so read queries stay single-table; `surfaced_at` keeps its meaning as ingestion time, leaving detection lag measurable. Every view now windows and buckets on `event_time`; cache keys are stamped with the data clock. `GET /api/v1/system/health` counts all events unfiltered. The live-feed payload (`LiveItem`, the Redis publish, and the WS frame) carries `event_time` alongside `surfaced_at` and no clock field. `seed.py` seeds only the admin user — there is no clock to seed. Token `iat` / `exp` remain on the wall clock in `security/tokens.py`; they must never use the data clock. |
| 2026-06-25 | **Ingest write-path added (Phase 2)** — additive. Four new components: **Ingest Route** (`api/ingest.py`, `api/ingest_schemas.py`) — token-gated `POST /api/v1/ingest`, flow enrich → score → atomic persist → publish new events to `garda:events:live` (commit-then-notify, same message shape the WS relay/frontend consume), idempotent on producer `transaction_id`, errors 200/400(FK)/401/422/502/503; **Ingest Auth** (`api/ingest_auth.py`) — bearer `GARDA_INGEST_TOKEN`, settings-only, constant-time; **ScoringClient** (`services/scoring_client.py`) — resilient httpx client (pooled `AsyncClient` on `app.state` via lifespan) for garda-ai-scoring `POST /v1/score`, bounded retries → `ScoringUnavailable`, 4xx-no-retry, X-Correlation-ID propagated — the backend's first **outbound** HTTP dependency; **IngestRepository** (`repositories/ingest.py`) — enrich lookups + idempotent batch persist (`ON CONFLICT (id) DO NOTHING ... RETURNING`, events for new ids, alerts for blocked, one transaction). New metrics `garda_ingest_transactions_total{result}` + `garda_ingest_scoring_latency_seconds`; config `scoring_url`/`scoring_token`/`ingest_token`/`scoring_timeout_s`/`scoring_retries`; `main.py` lifespan opens the pooled httpx client. The replay/read paths are unchanged; read re-anchoring onto ingest events is Phase 5. |
| 2026-06-23 | **Live WebSocket Relay rewritten** (`api/ws.py`): removed concurrent reader/writer tasks and bounded queue (`asyncio.Queue(maxsize=100)`) with drop-to-latest / `{"type":"resync"}` backpressure. Replaced with a single poll-and-forward loop (`pubsub.get_message(timeout=15)` → `send_text`). Root cause: the concurrent-task pattern delivered correctly under Starlette's in-process test transport but failed to deliver messages under uvicorn's real WebSocket transport. Backpressure is now the natural `send_text` await; clients still backfill gaps via `GET /transactions/live?after_seq=`. Covered by new real-against-uvicorn integration test `tests/test_ws_uvicorn.py`. |
