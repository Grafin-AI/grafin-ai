# Garda AI AML Platform — STRIDE Threat Model

**Version:** 2.0  
**Date:** 2026-08-08 (Updated for GCP Cloud Run deployment architecture)  
**Scope:** All deployed components — FastAPI backend, React SPA, Scoring Service, Ingest Job, Cloud SQL, Memorystore, nginx, GCP Cloud Run.

---

## System Overview

```
Browser (React SPA)
  |-- HTTPS --> nginx (reverse proxy)
                 |-- /api  --> FastAPI Backend (JWT-authenticated REST)
                 |-- /ws   --> FastAPI Backend (JWT-authenticated WebSocket)
                              |-- Cloud SQL (Postgres, parameterized SQL, source of truth)
                              |-- Memorystore (Redis: refresh tokens, cache, pub/sub garda:events:live)
                              |
                              |-- Scoring Service (HTTP, bearer scoring token)

External Producer (garda-ai-sim or real feed)
  |-- HTTPS --> Backend POST /api/v1/ingest (bearer ingest token)
                 |-- Scores batches via Scoring Service
                 |-- Persists events to Postgres
                 |-- Publishes to Redis pub/sub --> WS relay

Ingest Job (Cloud Run Job, one-shot seed)
  |-- Cloud SQL write (reference data load)
```

Trust boundaries: Internet / nginx perimeter; nginx / FastAPI internal; FastAPI / Postgres+Redis internal; Backend / Scoring Service internal (VPC).

---

## STRIDE Table

| Category | Threat | Current Mitigations |
|---|---|---|
| **Spoofing** | Attacker presents forged or replayed JWT to access API | JWT access tokens signed with `GARDA_JWT_SECRET` (from Secret Manager; fail-closed: refuses to boot if secret is missing or <32 chars). 15 min access TTL limits replay window. Refresh tokens stored in Redis and consumed with atomic GETDEL on rotation — a stolen refresh token can be used at most once before the legitimate holder's next use invalidates it. Logout explicitly revokes the refresh token from Redis. |
| **Spoofing** | Attacker guesses or brute-forces credentials | Passwords hashed with Argon2id. Per-IP login rate limiting via Redis fixed-window counter (10 attempts/min). |
| **Spoofing** | Attacker forges ingest or scoring bearer tokens | Ingest and scoring tokens are uniformly random, stored in Secret Manager, and supplied to Cloud Run services via secret_key_ref. Backend validates ingest token on every `POST /api/v1/ingest` request. Backend validates scoring token before calling the Scoring Service. |
| **Tampering** | Attacker modifies transaction or alert data in Postgres | Parameterized SQL only — no string-concatenated queries. Only two writers: Backend ingest path (guarded by ingest token) and Ingest Job (one-shot, service-account authenticated). FastAPI endpoints are read-oriented for analysts; writes are controlled and RBAC-guarded. |
| **Tampering** | Attacker injects malicious input via REST or WS | Pydantic V2 input validation on all request models enforced at the framework boundary before any business logic runs. |
| **Tampering** | Attacker intercepts Backend → Scoring Service communication | VPC Connector ensures traffic is internal to the VPC (no internet exposure). Optional: Backend can validate Scoring Service via mutual TLS (future hardening). |
| **Repudiation** | Analyst denies viewing or unmasking PII | Admin-only unmask operations are audited (server-side audit log). PII masking is server-side — the masked form is what leaves the API for analyst-role responses, so the unmasked access event is the only place PII is released. |
| **Repudiation** | Attacker denies abusing a refresh token | Refresh token rotation records each issuance; revocation on logout provides a clear audit trail in Redis (key presence/absence). |
| **Information Disclosure** | Analyst-role user reads raw PII (entity names, account IDs) | PII masking applied server-side before response serialisation. Unmask endpoint is admin-only (`require_role` default-deny RBAC), and unmasking is audited. |
| **Information Disclosure** | Attacker intercepts traffic between browser and server | nginx terminates TLS (HTTPS/WSS in production via managed Google certs). Security headers set by nginx: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`. |
| **Information Disclosure** | JWT token exposed in WebSocket URL query parameter | Access tokens are short-lived (15 min), limiting the exploit window if a `?token=` value reaches logs or proxies. (See Residual Risks.) |
| **Information Disclosure** | Redis contains live refresh tokens and rate-limit keys | Memorystore is on the private VPC, not exposed externally. Cloud Run services reach it via VPC Connector with internal traffic only. |
| **Information Disclosure** | Ingest or scoring bearer tokens exposed | Tokens are stored in Secret Manager with least-privilege IAM access. Services access via secret_key_ref (auto-injected at runtime, not in environment). Tokens rotate with secret version updates. |
| **Denial of Service** | Attacker floods `/login` to exhaust backend or lock accounts | Redis fixed-window rate limiter: 10 requests/IP/min on the login endpoint. |
| **Denial of Service** | Attacker floods arbitrary API endpoints | nginx rate limiting (configurable `limit_req`). Cloud Run auto-scales; `min_instances` keeps the service warm. `/healthz` endpoint checks Postgres and Redis connectivity. |
| **Denial of Service** | Attacker floods ingest endpoint with malformed requests | Ingest token validation occurs first; invalid tokens are rejected immediately. Pydantic validation of batch structure prevents large parsing errors. |
| **Elevation of Privilege** | Analyst-role user calls admin-only endpoints (unmask, user management) | `require_role` decorator on every protected endpoint; default-deny — any endpoint without an explicit role check is inaccessible to authenticated non-admin users. RBAC enforced at the FastAPI dependency layer, not just the frontend. |
| **Elevation of Privilege** | Unauthenticated caller accesses any data endpoint | JWT validation is a mandatory FastAPI dependency on all data routes; no data is reachable without a valid, non-expired access token. |
| **Elevation of Privilege** | Attacker reuses a rotated or logged-out refresh token to elevate session | Atomic GETDEL on refresh token consumption means a rotated token is deleted on first use. Logout explicitly deletes the key. Any attempt to reuse a consumed or revoked token returns 401. |
| **Elevation of Privilege** | Attacker calls Scoring Service directly (bypassing token validation) | Scoring Service has ingress set to internal-only (VPC Connector). No public URL. Backend service account has `roles/run.invoker` to call Scoring Service; other identities cannot invoke it. |

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
**Remediation:** Document the minimum recommended entropy (256-bit / 32-byte random value, e.g. `openssl rand -hex 32`) in the deployment runbook. Inject via Secret Manager, not a plain environment variable.

### 5. No per-user WebSocket connection cap — connection flooding via token abuse

**Risk:** An attacker holding a valid access token (or multiple tokens across accounts) can open an unbounded number of WS connections to the relay, exhausting file descriptors or memory.  
**Remediation:** Add a Redis counter keyed by `user_id` (or `token_jti`) that increments on WS connect and decrements on disconnect. Reject connections that exceed a configurable cap (e.g. 5 concurrent connections per user). Expire the counter key with a TTL as a safety backstop.

### 6. CORS allowlist must be set for the real frontend origin in production

**Risk:** An open or misconfigured CORS policy allows any origin to make credentialed cross-origin requests to the API.  
**Current state:** The codebase notes CORS is "to be set per deploy."  
**Remediation:** Set `allow_origins` in the FastAPI CORS middleware to the exact production frontend origin(s) — never `*` with `allow_credentials=True`. Validate this in a deployment checklist.

### 7. Ingest job must be kept secure

**Risk:** The ingest job has write access to Postgres. If compromised, it can inject malicious data.  
**Remediation:** The job is deployed as a Cloud Run Job with a dedicated service account that has only Cloud SQL access (no other cloud permissions). Jobs run one-shot with no public ingress. Audit all job executions via Cloud Logging.

---

## Threat Model Refresh for Phase 6 (GCP Deployment)

The architecture changed significantly in Phase 6 (polyrepo → GCP Cloud Run). The core STRIDE mitigations remain in place:
- Authentication via JWT (unchanged)
- PII masking server-side (unchanged)
- Parameterized SQL / input validation (unchanged)
- Rate limiting (unchanged)

New threat surface (GCP-specific):
- Workload Identity Federation (WIF) for CI/CD (no long-lived keys; short-lived OIDC tokens)
- VPC-internal communication (Backend → Scoring Service, all services → Cloud SQL/Memorystore)
- Secret Manager for secrets (centralized, least-privilege IAM)
- Cloud Run ingress controls (public backend/frontend, internal scoring)

A comprehensive re-derivation of STRIDE threats for the multi-service topology is recommended in Phase 7 or when security requirements escalate.

---

## SAST

Per-repository static analysis can be run at any time using the `security-sast` skill (`/security-sast`), which will scan the codebase for injection vulnerabilities, insecure dependencies, and misconfigured secrets.

---

## Revision Policy

This threat model should be re-evaluated after each major change in:
- Authentication architecture
- Data-flow paths
- Secret management
- Network topology
- New external dependencies or APIs
