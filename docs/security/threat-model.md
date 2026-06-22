# Garda AI AML Platform — STRIDE Threat Model

**Version:** 1.0  
**Date:** 2026-06-22  
**Scope:** All implemented and merged components — FastAPI backend, React SPA, ETL/replay pipeline, Postgres, Redis, nginx, docker-compose deploy.

---

## System Overview

```
Browser (React SPA)
  |-- HTTPS --> nginx
                 |-- /api  --> FastAPI (JWT-authenticated REST)
                 |-- /ws   --> FastAPI (JWT-authenticated WebSocket)
                              |-- Postgres (parameterized SQL, source of truth)
                              |-- Redis   (refresh tokens, rate-limit counters,
                                           pub/sub garda:events:live)
Pipeline worker (ETL + replay)
  |-- pg advisory lock (single producer)
  |-- writes events --> Postgres --> NOTIFY --> Redis pub/sub --> WS relay
```

Trust boundaries: Browser / nginx perimeter; nginx / FastAPI internal; FastAPI / Postgres+Redis internal; Pipeline worker / Postgres internal.

---

## STRIDE Table

| Category | Threat | Current Mitigations |
|---|---|---|
| **Spoofing** | Attacker presents forged or replayed JWT to access API | JWT access tokens signed with `GARDA_JWT_SECRET` (fail-closed: refuses to boot in non-dev if secret is default or <32 chars). 15 min access TTL limits replay window. Refresh tokens stored in Redis and consumed with atomic GETDEL on rotation — a stolen refresh token can be used at most once before the legitimate holder's next use invalidates it. Logout explicitly revokes the refresh token from Redis. |
| **Spoofing** | Attacker guesses or brute-forces credentials | Passwords hashed with Argon2id. Per-IP login rate limiting via Redis fixed-window counter (10 attempts/min). |
| **Tampering** | Attacker modifies transaction or alert data in Postgres | Parameterized SQL only — no string-concatenated queries. Pipeline worker holds a `pg_try_advisory_lock` (single producer) so only one writer can advance the event clock; atomic event-write + clock-advance prevents partial state. FastAPI endpoints are read-oriented for analysts; writes are controlled and RBAC-guarded. |
| **Tampering** | Attacker injects malicious input via REST or WS | Pydantic V2 input validation on all request models enforced at the framework boundary before any business logic runs. |
| **Repudiation** | Analyst denies viewing or unmasking PII | Admin-only unmask operations are audited (server-side audit log). PII masking is server-side — the masked form is what leaves the API for analyst-role responses, so the unmasked access event is the only place PII is released. |
| **Repudiation** | Attacker denies abusing a refresh token | Refresh token rotation records each issuance; revocation on logout provides a clear audit trail in Redis (key presence/absence). |
| **Information Disclosure** | Analyst-role user reads raw PII (entity names, account IDs) | PII masking applied server-side before response serialisation. Unmask endpoint is admin-only (`require_role` default-deny RBAC), and unmasking is audited. |
| **Information Disclosure** | Attacker intercepts traffic between browser and server | nginx terminates TLS (HTTPS/WSS in production). Security headers set by nginx: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`. |
| **Information Disclosure** | JWT token exposed in WebSocket URL query parameter | Access tokens are short-lived (15 min), limiting the exploit window if a `?token=` value reaches logs or proxies. (See Residual Risks.) |
| **Information Disclosure** | Redis contains live refresh tokens and rate-limit keys | Redis is on the internal Docker network, not exposed externally. |
| **Denial of Service** | Attacker floods `/login` to exhaust backend or lock accounts | Redis fixed-window rate limiter: 10 requests/IP/min on the login endpoint. |
| **Denial of Service** | Attacker floods arbitrary API endpoints | FastAPI is behind nginx; nginx can be configured with `limit_req` at the proxy layer. `/readyz` health endpoint checks both Postgres and Redis so orchestrators detect degradation. |
| **Denial of Service** | Pipeline replay worker produces duplicate or out-of-order events | `pg_try_advisory_lock` enforces single-producer. Commit-then-notify ordering ensures events are durable in Postgres before subscribers see them. |
| **Elevation of Privilege** | Analyst-role user calls admin-only endpoints (unmask, user management) | `require_role` decorator on every protected endpoint; default-deny — any endpoint without an explicit role check is inaccessible to authenticated non-admin users. RBAC enforced at the FastAPI dependency layer, not just the frontend. |
| **Elevation of Privilege** | Unauthenticated caller accesses any data endpoint | JWT validation is a mandatory FastAPI dependency on all data routes; no data is reachable without a valid, non-expired access token. |
| **Elevation of Privilege** | Attacker reuses a rotated or logged-out refresh token to elevate session | Atomic GETDEL on refresh token consumption means a rotated token is deleted on first use. Logout explicitly deletes the key. Any attempt to reuse a consumed or revoked token returns 401. |

---

## Residual Risks to Track

The following are known design tradeoffs. Each has a concrete remediation path.

### 1. SPA tokens in localStorage — XSS exfiltration risk

**Risk:** `localStorage` is accessible to any JavaScript running in the page origin. A successful XSS attack can exfiltrate both the access token and the refresh token.  
**Remediation:** Enforce a strict Content-Security-Policy header (restrict `script-src` to self + known hashes/nonces, eliminate `unsafe-inline`). For a higher-assurance deployment, move the refresh token to an `HttpOnly; Secure; SameSite=Strict` cookie and keep only the short-lived access token in memory (not localStorage).

### 2. WebSocket `?token=` query parameter leaks into logs and proxy records

**Risk:** The WS upgrade URL `wss://host/ws?token=<jwt>` is recorded verbatim in nginx access logs, upstream proxy logs, and potentially browser history. An attacker with log read access obtains a valid token.  
**Remediation (short-term):** Add `log_format` directives in nginx to scrub or redact the `token` query parameter. Add similar scrubbing in uvicorn/FastAPI access logging. The 15 min access TTL already limits the exploitation window.  
**Remediation (long-term):** Migrate WS authentication to the WebSocket subprotocol header (client sends token via `Sec-WebSocket-Protocol` on upgrade) or to a one-time ticket issued by a REST endpoint immediately before the WS connection, so no long-lived credential appears in the URL.

### 3. Default demo admin credential must be rotated before any non-demo use

**Risk:** The docker-compose deploy ships with `admin@garda.local / admin` as the seeded admin account. Any non-demo environment that does not rotate this credential is fully compromised on first access.  
**Remediation:** Add a pre-flight check (or compose entrypoint script) that refuses to start with the default admin password in production mode. Rotate the password and revoke all existing sessions as part of the initial production deployment runbook.

### 4. GARDA_JWT_SECRET strength in production

**Risk:** A weak or default JWT secret allows token forgery.  
**Current control (good):** The backend already fails closed — it refuses to start in non-dev mode if `GARDA_JWT_SECRET` is the default value or shorter than 32 characters.  
**Remediation:** Document the minimum recommended entropy (256-bit / 32-byte random value, e.g. `openssl rand -hex 32`) in the deployment runbook and inject via secrets manager, not a plain environment variable in the compose file.

### 5. No per-user WebSocket connection cap — connection flooding via token abuse

**Risk:** An attacker holding a valid access token (or multiple tokens across accounts) can open an unbounded number of WS connections to the relay, exhausting file descriptors or memory.  
**Remediation:** Add a Redis counter keyed by `user_id` (or `token_jti`) that increments on WS connect and decrements on disconnect. Reject connections that exceed a configurable cap (e.g. 5 concurrent connections per user). Expire the counter key with a TTL as a safety backstop.

### 6. CORS allowlist must be set for the real frontend origin in production

**Risk:** An open or misconfigured CORS policy allows any origin to make credentialed cross-origin requests to the API.  
**Current state:** The codebase notes CORS is "to be set per deploy."  
**Remediation:** Set `allow_origins` in the FastAPI CORS middleware to the exact production frontend origin(s) — never `*` with `allow_credentials=True`. Validate this in a deployment checklist.

### 7. Pipeline worker has no /metrics endpoint

**Note:** This is an observability gap, not a security issue. The ETL and replay worker do not currently expose a Prometheus `/metrics` endpoint, leaving resource utilisation and throughput unmonitored. Add a lightweight metrics exporter (e.g. `prometheus-client` with a WSGI sidecar) in a future iteration.

---

## SAST

Per-repository static analysis can be run at any time using the `security-sast` skill (`/security-sast`), which will scan the codebase for injection vulnerabilities, insecure dependencies, and misconfigured secrets.

---

## Revision Policy

This threat model should be reviewed and updated whenever:
- A new authentication or session mechanism is introduced.
- The data flow between components changes (new queues, new external services).
- PII handling logic is modified.
- The deployment topology changes (e.g., move from docker-compose to Kubernetes).
