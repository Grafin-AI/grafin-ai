# Grafin AI — Deployment & Infrastructure

**Status:** Local development (docker-compose) + GCP Cloud Run production deployment

This repo contains:
- Local development stack (docker-compose)
- Production IaC (Terraform for GCP Cloud Run)
- Per-service CI/CD workflows (in respective repos)
- Deployment runbook and documentation

## Local Development (docker-compose)

### Prerequisites

- Docker + Docker Compose
- The dataset at `../grafin-ai-data/HI-Small-ID/` (or set `GRAFIN_DATA_HOST_DIR` to another path).
  Switching datasets needs `make reset` (`docker compose down -v`): old rows live in the
  Postgres volume.
- Optional, for model scores (`GRAFIN_SCORER=precomputed`): `scores.csv` from
  `grafin-train export-scores --run <run-id>`, with `GRAFIN_SCORES_HOST_DIR` pointing at
  `../training/runs/<run-id>/scores`.
- Demo replay: `make demo-history` (validation days 2025-09-09..11, unpaced), then
  `make demo-test` (test period from 2025-09-12, speed 60).
- `.env` file with required secrets (see `.env.example`)

### Quick Start

```bash
# Copy example env and fill in secrets
cp .env.example .env

# Generate JWT secret (at least 32 chars) and paste into GRAFIN_JWT_SECRET
make seed-secret

# Start the full local stack
make up

# (Optional) Add simulation producer
make sim

# (Optional) Add Prometheus + Grafana observability
make obs
```

### Compose Services

| Service | Purpose | Port | Profile |
|---------|---------|------|---------|
| **postgres** | Database | — | default |
| **redis** | Cache + pub/sub | — | default |
| **backend** | FastAPI server | 8000 | default |
| **scoring** | Stateless scorer | — | default (internal only) |
| **frontend** | nginx + React SPA | 8080 | default |
| **ingest** | Reference data seed | — | default (one-shot) |
| **sim** | Local transaction producer | — | `sim` |
| **prometheus** | Metrics scraper | 9090 | `observability` |
| **grafana** | Dashboards | 3000 | `observability` |

### URLs (Local)

```
Dashboard:        http://localhost:8080
API docs:         http://localhost:8000/docs
Prometheus:       http://localhost:9090 (if --profile observability)
Grafana:          http://localhost:3000 (if --profile observability)
```

Default login: `admin@grafin.local` / `admin`

### Common Commands

```bash
# Start default stack (backend, frontend, scoring, postgres, redis, ingest seed)
make up

# Start with simulator
make sim

# Start with observability stack
docker compose --profile observability up

# Rebuild a service (e.g., after code changes)
docker compose up -d --build backend

# Stop everything
make down

# View logs
docker compose logs -f backend
docker compose logs -f frontend
```

### Environment Variables

See `.env.example` for the full list. Key secrets:
- `GRAFIN_JWT_SECRET` — Minimum 32 characters (for local dev, can be anything; for production, use Secret Manager)
- `GRAFIN_INGEST_TOKEN` — Bearer token for the `/api/v1/ingest` endpoint
- `GRAFIN_SCORING_TOKEN` — Bearer token for backend → scoring service auth
- `POSTGRES_USER`, `POSTGRES_PASSWORD` — Database credentials (default: `grafin`/`grafin`)

### Architecture (Local)

```
┌─────────────────┐
│  Browser        │
│  (localhost:    │
│   8080)         │
└────────┬────────┘
         │
         v
    ┌─────────┐
    │ nginx   │
    │frontend │
    └────┬────┘
         │ proxy to /api → backend:8000
         v
    ┌─────────────┐        ┌─────────┐
    │   FastAPI   │──────>│ Scoring │
    │  Backend    │        └─────────┘
    └────┬────────┘
         │
         v
    ┌─────────────┐     ┌────────┐
    │  Postgres   │     │  Redis │
    │   (Schema   │     │(Cache/ │
    │  +auth+     │     │ Pub/Sub)
    │  Events)    │     └────────┘
    └─────────────┘

Optional profiles:
─ sim: grafin-ai-sim producer → POST /api/v1/ingest
─ observability: Prometheus scrapes /metrics → Grafana displays
```

See `docs/c4/02-container.md` for the full C4 architecture.

---

## Production Deployment (GCP Cloud Run)

### Overview

Grafin AI runs on GCP Cloud Run with:
- **Backend API** — Public Cloud Run service
- **Frontend** — Public Cloud Run service (nginx reverse proxy)
- **Scoring Service** — Internal Cloud Run service
- **Migrate Job** — Cloud Run Job (schema migration)
- **Ingest Job** — Cloud Run Job (reference data seed)
- **Cloud SQL** — Managed PostgreSQL (private, VPC-only)
- **Memorystore** — Managed Redis (private, VPC-only)
- **Secret Manager** — Centralized secrets
- **Artifact Registry** — Image storage
- **VPC Connector** — Bridges Cloud Run to private databases

### Deployment Steps

**Full operator checklist:** See `docs/deploy/gcp-runbook.md` for detailed instructions.

Quick summary:
1. Create GCP project + enable APIs
2. Prepare Terraform variables (`terraform.tfvars`)
3. Set up remote state backend (GCS bucket)
4. **Phase 1:** `terraform apply -target=…artifact_registry…` (network, DB, secrets)
5. Push service images to Artifact Registry (via CI/CD or manual)
6. **Phase 2:** `terraform apply` (services, jobs, domain mappings)
7. Run `gcloud run jobs execute grafin-migrate` then `gcloud run jobs execute grafin-ingest`
8. Set up DNS records for custom domain
9. Test endpoints via HTTPS

### Workload Identity Federation (No Long-Lived Keys)

Each service repo's CI/CD (`deploy.yml`) authenticates to GCP via:
- GitHub Actions OIDC token
- Workload Identity Federation (WIF)
- Short-lived credentials (no API keys)

Operator sets up WIF once (see runbook step 4).

### Monitoring

- **Default:** Google Cloud Monitoring (free, built-in)
- **Optional:** Self-hosted Prometheus + Grafana (set `deploy_observability = true` in Terraform)

---

## CI/CD Workflows

Each service repo owns its pipeline:

| Repo | CI Workflow | Deploy Workflow |
|------|-------------|---|
| **grafin-ai-backend** | `test` + `lint` via `uv` + `pytest` + `ruff` | Build → push to Artifact Registry → `gcloud run deploy` |
| **grafin-ai-dashboard-web** | `test` + `build` via `npm` + `vitest` | Build → push to Artifact Registry → `gcloud run deploy` |
| **grafin-ai-scoring** | Inherited from Phase 1 | Build → push to Artifact Registry → `gcloud run deploy` |
| **grafin-ai-ingest** | Inherited from Phase 1 | Build → push to Artifact Registry → `gcloud run jobs deploy` |

All deploy workflows:
- Trigger on `push` to `main`
- Use **Workload Identity Federation** for GCP auth (no secrets)
- Reference repo `vars` (GCP_PROJECT, GCP_REGION) and `secrets` (GCP_WIF_PROVIDER, GCP_DEPLOYER_SA)

---

## Docker Image Building

All services build in their respective repos. The frontend uses **nginx templating** for multi-environment:

- **Local:** Frontend service in compose sets `BACKEND_URL=http://backend:8000`
- **Cloud:** Terraform template injects backend's public Cloud Run URL into the nginx config at deploy time

The `nginx:alpine` image's entrypoint automatically renders `/etc/nginx/templates/*.template` files via `envsubst`, substituting `${BACKEND_URL}` while preserving nginx built-in variables (`$host`, `$http_upgrade`, etc.).

---

## Project Structure

```
grafin-ai-deploy/
├── docker-compose.yml          # Local dev stack definition
├── .env.example               # Environment variable template
├── Makefile                   # Common tasks
├── README.md                  # This file
├── terraform/                 # GCP IaC (Terraform)
│   ├── main.tf                # Service + job definitions
│   ├── network.tf             # VPC + VPC Connector
│   ├── database.tf            # Cloud SQL + Memorystore
│   ├── secrets.tf             # Secret Manager integration
│   ├── variables.tf           # Input variables
│   ├── outputs.tf             # Output values
│   └── terraform.tfvars.example # Example configuration
├── observability/             # Prometheus + Grafana config
│   ├── prometheus.yml         # Scrape targets
│   └── grafana/               # Dashboard provisioning
├── docs/
│   ├── c4/                    # C4 architecture diagrams
│   │   ├── 01-context.md      # System context
│   │   └── 02-container.md    # Container topology (GCP)
│   ├── deploy/
│   │   └── gcp-runbook.md     # Operator deployment guide
│   ├── security/              # Threat model, security notes
│   └── superpowers/           # Planning & design specs
```

---

## Key Design Decisions

### Why GCP Cloud Run?

- **Serverless:** Scale to zero, pay only for execution time
- **Managed:** TLS, custom domains, automatic scaling built-in
- **Multi-service:** Each service (backend, frontend, scoring) runs independently with its own resource constraints
- **Networking:** VPC Connector bridges to private Cloud SQL + Memorystore
- **No long-lived keys:** Workload Identity Federation for CI/CD

### Why Nginx Templating?

The frontend nginx config must point to different backend URLs depending on the environment:
- **Local:** `http://backend:8000` (docker-compose service name)
- **Cloud:** `https://api.grafin.example.com` (Cloud Run backend URL)

Using `${BACKEND_URL}` templating means one image works everywhere.

### Why Two-Phase Terraform Apply?

Cloud Run services validate image existence at deployment time. The two-phase approach:
1. **Phase 1:** Provision infrastructure (VPC, DB, Artifact Registry, secrets) — images don't exist yet
2. **Push images** to Artifact Registry
3. **Phase 2:** Deploy services/jobs — images now exist and are validated

---

## Troubleshooting

### Local Stack Issues

**Services fail to start:**
```bash
# Check logs
docker compose logs -f

# Verify health
docker compose ps

# Rebuild and restart
docker compose down
docker compose up --build
```

**Port conflicts:**
- Change ports in `docker-compose.yml` or use environment variables
- Check: `lsof -i :8000` or `lsof -i :8080`

**Database migration fails:**
- Backend service should auto-run `alembic upgrade head` on startup
- Check logs: `docker compose logs backend`

### Production Deployment Issues

See `docs/deploy/gcp-runbook.md` → **Troubleshooting** section.

---

## Contributing

1. Make changes in the respective service repo
2. Submit a PR (triggers per-repo CI workflows)
3. Merge to `main` (triggers per-repo deploy workflow)
4. Verify deployment in GCP via `gcloud run services describe <service>`

---

## References

- **Local architecture:** `docs/c4/02-container.md`
- **GCP deployment guide:** `docs/deploy/gcp-runbook.md`
- **Security threat model:** `docs/security/threat-model.md`
- **Service repos:**
  - Backend: https://github.com/your-org/grafin-ai-backend
  - Frontend: https://github.com/your-org/grafin-ai-dashboard-web
  - Scoring: https://github.com/your-org/grafin-ai-scoring
  - Ingest: https://github.com/your-org/grafin-ai-ingest
  - Sim: https://github.com/your-org/grafin-ai-sim
