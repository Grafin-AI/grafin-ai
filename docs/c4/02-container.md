# Garda AI — C4 Level 2: Container

**Date:** 2026-08-08 (GCP Cloud Run deployment topology)
**Source:** Authored from the approved design (`docs/superpowers/specs/2026-06-25-deploy-split-design.md`). Component + Code levels are generated per repo (bottom-up) after implementation.

## Containers (GCP Cloud Run)

| Container | Repo / Service | Tech | Responsibility | Ingress |
|---|---|---|---|---|
| **Dashboard Web** | `garda-ai-dashboard-web` / Cloud Run Service | React 18, Vite, TanStack Query, nginx | SPA frontend + reverse proxy; terminates TLS; proxies `/api` + `/ws` to backend. | Public (`https://app.<domain>`) |
| **Backend API** | `garda-ai-backend` / Cloud Run Service | FastAPI, SQLAlchemy 2.0, asyncpg | REST aggregations, WS relay, auth/RBAC, PII masking. **Owns DB schema + migrations.** Token-gated `POST /api/v1/ingest` write-path: scores each batch via scoring service, persists transactions/events/alerts, publishes to Redis for WS relay. | Public (`https://api.<domain>`) |
| **Scoring Service** | `garda-ai-scoring` / Cloud Run Service | FastAPI (stateless) | Stateless scorer exposing `POST /v1/score`; returns scores/labels for a batch. Called by backend ingest path via internal URL. | Internal (VPC only) |
| **Migrate Job** | `garda-ai-backend` / Cloud Run Job | FastAPI + Alembic | One-shot schema migration: `alembic upgrade head`. Runs before ingest + services take traffic. | None (one-shot) |
| **Ingest Job** | `garda-ai-ingest` / Cloud Run Job | Python | Reference dataset seed: loads HI-Small transactions into Postgres. Runs after migrate. | None (one-shot) |
| **Cloud SQL** | GCP Managed Service | PostgreSQL 16 | Source of truth: accounts, transactions, events, alerts, users. Private IP via VPC connector. | VPC Private |
| **Memorystore** | GCP Managed Service | Redis 7 | Pub/sub (live events), cache, rate-limit, refresh-token store. Private IP. | VPC Private |
| **Secret Manager** | GCP Managed Service | — | Centralized secrets: JWT secret, ingest token, scoring token, DB password. | Service-account scoped |
| **Artifact Registry** | GCP Managed Service | Docker repos | Stores built images for backend, frontend, scoring, ingest services + jobs. | Service-account scoped |
| **VPC Connector** | GCP Managed Service | Serverless VPC Access | Bridges Cloud Run to private Cloud SQL + Memorystore. | VPC only |

## Diagram

```mermaid
C4Container
    title Container — Garda AI AML Platform (GCP Cloud Run)

    Person(analyst, "AML Analyst", "Masked PII")
    Person(admin, "Platform Admin", "Unmasked PII (audited)")
    System_Ext(sim, "garda-ai-sim", "Local producer — streams via /api/v1/ingest")

    System_Boundary(gcp, "GCP Project") {
        System_Boundary(pubsub, "Public (TLS)") {
            Container(web, "Dashboard Web", "nginx + React 18", "SPA frontend, reverse proxy to backend")
            Container(api_pub, "Backend API (public)", "Cloud Run Service", "REST reads, ingest writes, WS relay")
        }

        System_Boundary(vpcnet, "VPC Network") {
            Container(scoring, "Scoring Service", "Cloud Run Service", "POST /v1/score (internal ingress only)")
            ContainerDb(sql, "Cloud SQL", "PostgreSQL 16", "Schema, accounts, transactions, events, alerts")
            ContainerDb(redis, "Memorystore", "Redis 7", "Pub/sub (live), cache, tokens")
            Container(vpc_conn, "VPC Connector", "Serverless Access", "Bridges Cloud Run to private SQL/Redis")
        }

        Container(migrate_job, "Migrate Job", "Cloud Run Job", "alembic upgrade head (pre-deploy init)")
        Container(ingest_job, "Ingest Job", "Cloud Run Job", "Reference seed: loads HI-Small")
        Container(secrets, "Secret Manager", "Secrets", "JWT secret, ingest token, scoring token, DB password")
        Container(registry, "Artifact Registry", "Docker repos", "backend, frontend, scoring, ingest images")
    }

    Rel(analyst, web, "Uses", "HTTPS/WSS (TLS)")
    Rel(admin, web, "Operates", "HTTPS/WSS (TLS)")
    Rel(web, api_pub, "Proxied by nginx", "HTTP (same-origin)")

    Rel(sim, api_pub, "Ingest batches", "HTTPS /api/v1/ingest, bearer token")
    Rel(api_pub, scoring, "Scores batches", "HTTP /v1/score, bearer token, via VPC")
    Rel(api_pub, sql, "Reads/writes", "SQL via VPC connector")
    Rel(api_pub, redis, "Cache, tokens, sub/pub", "RESP via VPC connector")

    Rel(migrate_job, sql, "Runs migrations", "SQL")
    Rel(ingest_job, sql, "Loads reference data", "SQL")

    Rel(secrets, api_pub, "Token/secret refs", "IAM service account")
    Rel(secrets, scoring, "Scoring token", "IAM service account")
    Rel(secrets, ingest_job, "DB password", "IAM service account")

    Rel(registry, web, "Deployed from", "Cloud Run pull")
    Rel(registry, api_pub, "Deployed from", "Cloud Run pull")
    Rel(registry, scoring, "Deployed from", "Cloud Run pull")
    Rel(registry, ingest_job, "Deployed from", "Cloud Run pull")

    UpdateLayoutConfig($c4ShapeInRow="2", $c4BoundaryInRow="1")
```

## Local Development (docker-compose)

For local development, a mirror stack runs via `docker-compose`:
- `postgres:16-alpine` (same schema as Cloud SQL)
- `redis:7-alpine` (same channel/cache as Memorystore)
- `backend` service (migrates, seeds, serves)
- `scoring` service (internal to compose network)
- `frontend` service (nginx with `${BACKEND_URL}=http://backend:8000`)
- Optional `ingest` one-shot (loads reference seed)
- Optional `sim` profile (streams via `/api/v1/ingest`)
- Optional `observability` profile (Prometheus + Grafana)

**Run locally:**
```bash
cp .env.example .env                          # set secrets/tokens
make up                                       # default stack (no sim, no observability)
make up-sim                                   # add sim producer
make obs                                      # add Prometheus/Grafana
```

See `README.md` for full quickstart.

## Critical flows

**Live transaction (commit-then-notify):**
Backend ingest → score via scoring service → INSERT `transaction_events` + alerts → **COMMIT** (Postgres durable) → publish to Redis `garda:events:live` → WS relay → Dashboard. On reconnect, dashboard backfills via `GET /transactions/live?after_seq=` from Postgres. Postgres is authoritative; WS is notification only.

**Dashboard read:** Dashboard → Backend REST → SQL aggregation over persisted events. Redis-cached per time bucket.

## Deployment flow

1. **Build phase (per repo CI):** Each service repo runs `.github/workflows/ci.yml` (test/lint) and `.github/workflows/deploy.yml` on push to `main`.
   - Deploy workflow: authenticate via Workload Identity Federation, build image, push to Artifact Registry.
2. **Terraform provisioning:** `garda-ai-deploy/terraform/` provisions GCP infrastructure: networking, Cloud SQL, Memorystore, Secret Manager, services, jobs.
3. **Deploy-init jobs:** Operator runs `gcloud run jobs execute garda-migrate` then `gcloud run jobs execute garda-ingest` to prepare data.
4. **Service deployment:** Backend, frontend, and scoring services auto-deploy from Artifact Registry on push (or manual trigger).

## Notes

- **Service-to-service auth:** Backend → scoring uses HTTP with bearer token (scoring token from Secret Manager). Backend and scoring are in the same VPC via VPC connector.
- **No long-lived API keys:** All GCP authentication is via Workload Identity Federation; CI/CD workflows assume GitHub Actions' OIDC token exchange for short-lived GCP credentials.
- **Frontend templating:** nginx image uses env substitution for the backend upstream (`${BACKEND_URL}`). Local compose sets it to `http://backend:8000`; Terraform template injects the backend Cloud Run URL.
- **Secrets management:** All secrets (JWT, ingest token, scoring token, DB password) are stored in GCP Secret Manager. Service accounts have least-privilege access (IAM roles).
- **Data residency:** All data persists in Cloud SQL + Memorystore within the GCP project region.
- **Observability:** Cloud Monitoring + optional self-hosted Prometheus/Grafana (controlled via Terraform `deploy_observability` variable).

> **Updated 2026-08-08 (Phase 6 — Deploy):** Moved from polyrepo compose to GCP Cloud Run. Pipeline containers (ETL, replay) deleted. Each service owns CI/CD. Nginx templated for multi-environment.

## Implementation status (as of 2026-08-08)

| Component | Status | Evidence |
|---|---|---|
| Backend API | ✅ Implemented | `garda-ai-backend` with per-repo CI + GCP deploy workflow |
| Frontend SPA | ✅ Implemented | `garda-ai-dashboard-web` with nginx templating + per-repo CI + deploy workflow |
| Scoring Service | ✅ Implemented | `garda-ai-scoring` with per-repo CI + deploy workflow |
| Ingest Job | ✅ Implemented | `garda-ai-ingest` with per-repo CI + deploy workflow |
| Migrate Job | ✅ Implemented | Alembic integration in backend, deployed as Cloud Run Job |
| Local Compose | ✅ Working | `docker-compose.yml` with `sim` and `observability` profiles |
| GCP Terraform IaC | ✅ Authored | `garda-ai-deploy/terraform/` (validate + plan ready; apply is operator step) |
| CI/CD Workflows | ✅ Wired | 4 service repos with `.github/workflows/{ci,deploy}.yml` |
| Docs (C4 + Runbook) | ✅ Updated | This file + `docs/deploy/gcp-runbook.md` |

Deployment to live GCP is the operator's step (requires GCP project, Workload Identity Federation setup, domain + DNS, and running `terraform apply` + job init).
