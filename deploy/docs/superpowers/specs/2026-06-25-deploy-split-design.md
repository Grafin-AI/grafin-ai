# Deploy Split — Local Compose + GCP Cloud Run IaC (Phase 6)

**Date:** 2026-06-25
**Status:** Approved (brainstorming)
**Scope:** `garda-ai-deploy` (compose + IaC + docs) and per-service deploy wiring in
`garda-ai-backend`, `garda-ai-dashboard-web`, `garda-ai-scoring`, `garda-ai-ingest`.
**Anchor spec:** `docs/superpowers/specs/2026-06-25-platform-rearchitecture-design.md`
**Depends on:** Phases 1–5 (the target service set exists; the pipeline is deleted).

Phase 6 — the final re-architecture phase — makes each service independently deployable and slims
`garda-ai-deploy` to **shared infra IaC + a local-dev compose**. It is no longer the deploy
mechanism: each service repo owns its Dockerfile + CI/CD and deploys itself to **GCP Cloud Run**.

## Decisions (settled in brainstorming)

- **Platform:** GCP Cloud Run (serverless containers, scale-to-zero, managed TLS + custom domain).
- **Deployed:** `backend` (public), `scoring` (**private/internal** ingress), `frontend` (public
  nginx SPA + reverse-proxy), `ingest` (Cloud Run **Job**), managed **Cloud SQL** (Postgres) +
  **Memorystore** (Redis).
- **Local only:** `garda-ai-sim` — never deployed; run via `uv run garda-sim` against the deployed
  backend's public `/ingest` URL (ingest token). It is an **optional compose profile** for local runs.
- **Observability (Prometheus + Grafana):** switchable — a `--profile observability` in compose
  (off by default) and a `deploy_observability` Terraform variable (default **false** → rely on
  Cloud Monitoring / Google Managed Prometheus; **true** → optional self-hosted module).
- **Frontend hosting:** the **nginx container** (same-origin: serves the SPA and reverse-proxies
  `/api` + `/ws` to the backend — no CORS, no WS-origin rework).
- **Deploy-init jobs:** a `migrate` Cloud Run Job (Alembic `upgrade head`) and an `ingest` Cloud
  Run Job (reference seed), run before the services take traffic.

---

## ① Local compose rework — `garda-ai-deploy/docker-compose.yml`

The compose is now **local-dev only** (full stack on a laptop; also how you test ingestion against
a local DB). Changes:

- **Remove** the `etl` and `replay` services (the deleted pipeline). The transactions bulk-load and
  the replay worker are gone; events now arrive via the sim → `/ingest` path.
- **Add `scoring`** (`build: ../garda-ai-scoring`, `GARDA_SCORING_TOKEN`), reachable by the backend
  at `http://scoring:8000`. Not published to the host (internal to the compose network).
- **Add the backend's ingest env:** `GARDA_SCORING_URL=http://scoring:8000`,
  `GARDA_SCORING_TOKEN`, `GARDA_INGEST_TOKEN` (all from `.env`). Keep the existing DB/Redis/JWT env.
  Backend `depends_on` now includes `scoring` (service_started) and the `ingest` seed
  (service_completed_successfully) so a fresh stack has reference data before the sim streams.
- **Replace `etl` with an `ingest` one-shot** (`build: ../garda-ai-ingest`,
  `command: uv run garda-ingest`, `restart: "no"`, mounts the HI-Small data read-only,
  `GARDA_DATABASE_URL`, `GARDA_DATA_DIR=/data`). Runs once against local Postgres after a `migrate`
  step. Depends on `postgres` healthy + the migration applied.
- **Migrations:** the backend already runs Alembic at startup in local dev (unchanged); the `ingest`
  seed depends on the schema existing. (If the backend does not auto-migrate, add a one-shot
  `migrate` service running `alembic upgrade head`; confirm the current local behavior in the plan.)
- **Add `sim` behind an optional profile** (`profiles: ["sim"]`, `build: ../garda-ai-sim`,
  `command: uv run garda-sim`, `GARDA_INGEST_URL=http://backend:8000/api/v1/ingest`,
  `GARDA_INGEST_TOKEN`, mounts the data read-only). Off by default;
  `docker compose --profile sim up sim` streams into the local stack.
- **Move `prometheus` + `grafana` behind `profiles: ["observability"]`** (off by default).
- **`.env.example`** gains `GARDA_SCORING_TOKEN`, `GARDA_INGEST_TOKEN` (and keeps the existing
  `GARDA_JWT_SECRET`, Postgres creds). Document the new profiles in the compose section of the README.

**Verification:** `docker compose config` is valid; `docker compose up` (default profiles) brings up
postgres, redis, scoring, backend, frontend + runs the ingest seed once; `--profile observability`
adds prom/grafana; `--profile sim` streams transactions. The old `etl`/`replay` are gone.

## ② GCP Cloud Run IaC — `garda-ai-deploy/terraform/`

Authored with the cloud-infrastructure / `terraform-specialist` plugin. Bar for this phase:
**`terraform validate` + `terraform plan` clean** against an example `terraform.tfvars`. A live
`apply` is the operator's step (needs a GCP project, billing, enabled APIs, and a domain).

Resources (modularized where it helps):
- **Project wiring:** `google` provider, required-APIs enablement (`run`, `sqladmin`,
  `redis`, `vpcaccess`, `secretmanager`, `artifactregistry`, `compute`).
- **Artifact Registry** Docker repository (one, region-scoped) for the 4 images.
- **Networking:** a VPC + a **Serverless VPC Access connector** so Cloud Run can reach the private
  Cloud SQL + Memorystore. Cloud SQL uses **private IP** (no public exposure).
- **Cloud SQL** — PostgreSQL 16 instance, database `garda`, a `garda` user; password in Secret
  Manager. Private IP via the VPC.
- **Memorystore** — Redis instance (basic tier), private, in the VPC.
- **Secret Manager** secrets: `garda-jwt-secret`, `garda-ingest-token`, `garda-scoring-token`,
  `garda-db-password` (+ the assembled `GARDA_DATABASE_URL`/`GARDA_REDIS_URL` as needed). Cloud Run
  services reference them as env via secret refs. **No secrets in tfvars or state in plaintext**
  (create secret *versions* out-of-band or via `google_secret_manager_secret_version` fed from a
  sensitive variable; document the trade-off).
- **Cloud Run services:**
  - `backend` — ingress **all** (public), `min_instances = 1` (keep the WS relay + Redis
    subscription warm), VPC connector attached, env from secrets + `GARDA_SCORING_URL` = the
    scoring service's internal URL, service account with `roles/cloudsql.client` +
    `secretmanager.secretAccessor`.
    WebSockets: request timeout raised (e.g. 3600s) for the `/ws/live` relay.
  - `scoring` — ingress **internal** (no public URL), VPC connector, `GARDA_SCORING_TOKEN` from
    secret. Backend → scoring auth: the scoring token (and optionally Cloud Run service-to-service
    IAM: backend SA granted `roles/run.invoker` on scoring).
  - `frontend` — ingress **all** (public), nginx image; `min_instances = 0` fine. Its nginx
    upstream for `/api` + `/ws` is the backend's public URL (templated at build/deploy — see ③).
- **Cloud Run Jobs:**
  - `migrate` — the backend image, `command: alembic upgrade head`, VPC connector + Cloud SQL access.
  - `ingest` — the ingest image, `command: garda-ingest`, VPC connector + Cloud SQL access, the
    reference CSV baked into the image or mounted from a bucket (document the choice — for the demo,
    baked-in is simplest; note the image size trade-off).
- **Custom domain + TLS:** Cloud Run **domain mappings** (`app.<domain>` → frontend,
  `api.<domain>` → backend) with Google-managed certs. Document the required DNS records.
- **Observability (switchable):** `variable "deploy_observability" { default = false }`. When
  `false`, no self-hosted stack — rely on Cloud Monitoring + (optional) Google Managed Prometheus
  scraping the backend/scoring `/metrics`. When `true`, an optional module provisions a self-hosted
  Prometheus + Grafana (the terraform-specialist picks the leanest GCP-native shape — e.g. a small
  GCE VM or a Cloud Run Grafana against Managed Prometheus). Keep it a clean on/off module boundary.
- **Outputs:** the service URLs, the Artifact Registry repo path, the DB connection name, and the
  domain-mapping DNS targets.

**Variables (example `terraform.tfvars.example`):** `project_id`, `region`, `domain`,
`deploy_observability`, image tags, instance sizes. Secrets are provided as *sensitive* variables
or created out-of-band (documented), never committed.

## ③ Per-service deploy wiring

Each deployable repo owns its Dockerfile (all present) + CI/CD:

- **Add CI where missing:** `garda-ai-backend/.github/workflows/ci.yml` and
  `garda-ai-dashboard-web/.github/workflows/ci.yml` (test/lint/build) — mirror the
  scoring/ingest/sim CI pattern. (backend: uv + pytest + ruff; frontend: `npm ci`/`npm install` +
  `npm test` + `npm run build`.) Move the intent of the legacy `garda-ai-deploy/ci/*.yml` into the
  repos; then **delete `garda-ai-deploy/ci/`** (and `ci/pipeline.yml`, now dead).
- **Add a deploy workflow** to the 4 deployable repos
  (`backend`, `frontend`, `scoring`, `ingest`): `.github/workflows/deploy.yml`, on push to `main`
  (or a release tag) — authenticate to GCP via **Workload Identity Federation** (no long-lived
  keys), build the image, push to Artifact Registry, then `gcloud run deploy`
  (or `deploy-cloudrun` action) for the services / `gcloud run jobs deploy` for `ingest`. Guard on
  repo-scoped secrets/vars (`GCP_PROJECT`, `GCP_WIF_PROVIDER`, `GCP_SA_EMAIL`, region). Document
  that these are set by the operator once GCP exists.
- **Frontend nginx upstream:** `nginx.conf`'s `/api` + `/ws` `proxy_pass` must target the backend's
  public URL in the cloud. Make it **templated** — an `envsubst` at container start (or a build arg
  `BACKEND_URL`) so the same image works locally (`http://backend:8000`) and in the cloud
  (`https://api.<domain>`). Preserve WS upgrade headers (`Upgrade`/`Connection`) in the `/ws` block.
  (Confirm the current `nginx.conf` proxy blocks in the plan and templatize them.)
- **`garda-ai-sim`:** no deploy workflow (never deployed). Keep its CI. Its README documents pointing
  `GARDA_INGEST_URL` at the deployed backend.

## ④ Docs

- **C4 `docs/c4/02-container.md`:** replace the compose-centric topology with the GCP Cloud Run
  deployment (public backend/frontend, private scoring, jobs for migrate/ingest, Cloud SQL +
  Memorystore + VPC connector + Secret Manager, sim as an external local producer). Mark the old
  pipeline containers removed.
- **Deployment runbook** (`docs/deploy/gcp-runbook.md`): the operator steps —
  create project, enable billing + APIs, set up Workload Identity Federation for the repos, provide
  the domain + DNS, `terraform apply`, run the `migrate` + `ingest` jobs, deploy the services, then
  run the sim locally. Include the "what only you can do" checklist.
- **README:** update the local-dev quickstart for the new compose (profiles for `sim` /
  `observability`), and point to the runbook for cloud deploy.
- **Purge remaining pipeline references** across deploy docs/config (compose done in ①; scan
  Makefile, README, prometheus scrape targets for `etl`/`replay`/`pipeline`).

## Sequencing & decomposition

One spec (this file), executed as **three plans + a docs pass**, in order:
1. **Compose rework** (`garda-ai-deploy/docs/superpowers/plans/2026-06-25-deploy-compose.md`) —
   lowest-risk, immediately verifiable locally.
2. **GCP IaC** (`.../plans/2026-06-25-deploy-gcp-iac.md`) — Terraform, `validate` + `plan` bar,
   `terraform-specialist` implementer.
3. **Per-service deploy wiring** (`.../plans/2026-06-25-deploy-service-cicd.md`) — CI where missing,
   deploy workflows, templated nginx upstream.
4. **Docs** — folded into the above plans' final tasks (C4 + runbook + README + pipeline purge).

Each plan is subagent-driven with review gates (the IaC gets a `cloud-architect` / security pass —
public-vs-private ingress, secret handling, least-privilege service accounts, no long-lived keys).

## Testing / verification bar (per plan)

- **Compose:** `docker compose config` valid; a default `up` yields a working stack (backend
  reachable, ingest seed completes, frontend serves); profiles toggle sim / observability. The old
  `etl`/`replay` are absent.
- **IaC:** `terraform fmt -check`, `terraform validate`, and `terraform plan` (with the example
  tfvars) succeed; the expert review confirms ingress/secret/IAM posture. **No live apply** here.
- **CI/CD:** the workflows are syntactically valid (actionlint or a dry parse); the deploy
  workflows are documented as requiring operator-provided GCP identity. The frontend image builds
  with the templated nginx and serves locally.

## Out of scope (YAGNI / operator's step)

- **The live cloud deployment itself** — creating the GCP project, billing, APIs, Workload Identity
  Federation, DNS/domain, and running `terraform apply` + the jobs. This spec delivers
  authored-and-validated IaC/CI + a runbook; the apply is the operator's.
- **Autoscaling tuning, CDN in front of the frontend, multi-region, blue/green** — later; Cloud Run
  defaults + `min_instances` suffice for the demo.
- **A managed message queue** between sim and backend — still direct HTTP `/ingest` (anchor decision).
- **Migrating secrets to a full vault / rotation policy** — Secret Manager with manual versions is
  enough for the demo; rotation is future.
