# Garda AI — GCP Cloud Run Terraform

Provisions the Garda platform on **GCP Cloud Run**:

- **3 services:** `garda-backend` (public, `min_instances=1`, WebSocket-friendly 3600s
  timeout), `garda-scoring` (`INGRESS_TRAFFIC_INTERNAL_ONLY`, only reachable in-network),
  `garda-frontend` (public nginx).
- **2 jobs:** `garda-migrate` (`alembic upgrade head`), `garda-ingest` (loads the
  reference dataset).
- **Data:** Cloud SQL Postgres 16 (private IP only) + Memorystore Redis (private
  service access) — both reached from Cloud Run through a Serverless VPC Access
  connector.
- **Supporting:** Secret Manager, Artifact Registry, VPC + subnet + PSA range,
  optional custom-domain mappings, optional self-hosted observability VM.

## Layout

| File | Concern |
| --- | --- |
| `versions.tf` | Terraform + `google`/`google-beta` provider pins |
| `variables.tf` | Inputs (project, region, domain, image tags, toggles, secrets) |
| `apis.tf` | `google_project_service` enablement |
| `network.tf` | VPC, subnet, Serverless VPC Access connector, Private Services Access |
| `registry.tf` | Artifact Registry docker repo |
| `secrets.tf` | Secret Manager secrets + versions (from sensitive vars) |
| `iam.tf` | Per-workload service accounts + least-privilege role bindings |
| `database.tf` | Cloud SQL Postgres instance + database + user |
| `redis.tf` | Memorystore Redis |
| `cloudrun.tf` | Backend / scoring / frontend Cloud Run services |
| `jobs.tf` | `migrate` + `ingest` Cloud Run Jobs |
| `domains.tf` | Cloud Run domain mappings (`app.` / `api.`), gated on `var.domain` |
| `observability.tf` | Optional self-hosted Prometheus + Grafana VM, gated on `var.deploy_observability` |
| `outputs.tf` | Service URLs, AR repo, DB connection name, domain DNS targets |

## Validate (no GCP credentials required)

`terraform validate` does **not** contact GCP, so it runs anywhere:

```bash
cd terraform
terraform fmt -check
terraform init -backend=false
terraform validate   # -> "Success! The configuration is valid."
```

> OpenTofu (`tofu`) is a drop-in for `fmt`/`validate`/`init` if you don't have the
> HashiCorp `terraform` binary.

## Operator apply path (requires GCP credentials)

`terraform plan` / `apply` are the **operator's** step — they need a real GCP
project, billing, and credentials.

1. **Authenticate** to GCP: `gcloud auth application-default login` (or a service
   account key / Workload Identity Federation in CI).
2. **Provide non-secret inputs** via `terraform.tfvars` (copy from
   `terraform.tfvars.example`) — set `project_id`, images, `domain`, toggles.
3. **Provide secrets out-of-band** — do NOT commit them. Use either:
   - `TF_VAR_jwt_secret`, `TF_VAR_ingest_token`, `TF_VAR_scoring_token`,
     `TF_VAR_db_password` environment variables, or
   - a `secrets.auto.tfvars` file (gitignored by `*.auto.tfvars`).
4. **Apply in two phases** (Cloud Run validates that each image exists at create
   time, but a clean project's Artifact Registry is empty on the first run):
   1. **Phase 1 — infra + registry first:** create the Artifact Registry repo (and
      the network/DB if you want them warming up):
      ```bash
      terraform apply \
        -target=google_artifact_registry_repository.docker \
        -target=google_service_networking_connection.psa \
        -target=google_sql_database_instance.pg
      ```
   2. **Push all four images** (`backend`, `scoring`, `frontend`, `ingest`) to the
      repo — via the per-repo CI or manually with `docker push` / `gcloud`. The
      `artifact_repo` output gives the base path.
   3. **Phase 2 — full apply:** now that every image exists, apply everything
      (services + jobs included):
      ```bash
      terraform apply
      ```
5. **Run deploy-init jobs before first traffic:**
   ```bash
   gcloud run jobs execute garda-migrate --region <region> --wait
   gcloud run jobs execute garda-ingest  --region <region> --wait
   ```
   The backend also self-migrates on start (alembic is idempotent, so the explicit
   `migrate` job is a harmless, ordered belt-and-suspenders step). The `ingest`
   image bundles the reference CSV; no extra mount is required for the demo.
6. Cloud Run then serves the three services; if `domain` is set, create the DNS
   records surfaced by the `domain_dns_app` / `domain_dns_api` outputs.

## Security posture

- **scoring** is `INGRESS_TRAFFIC_INTERNAL_ONLY` — the network gate keeps it off
  the public internet. The backend reaches it over the VPC connector (backend
  `egress = ALL_TRAFFIC` so the call to scoring's `*.run.app` URL is routed
  through the connector and seen as internal). The `run.invoker` binding is
  `allUsers`, which does **not** expose scoring publicly (ingress still blocks
  that); it only drops the Google OIDC ID-token requirement so the app's
  `GARDA_SCORING_TOKEN` header is the real service-to-service auth.
- **Cloud SQL + Memorystore are private** (`ipv4_enabled=false`, PSA + VPC
  connector). No public database endpoint.
- **Secrets** live in Secret Manager and are injected via
  `value_source.secret_key_ref` — never as plaintext env values. This includes
  the assembled DB DSN (`garda-database-url`), so the password never rides in a
  plaintext `GARDA_DATABASE_URL` env var readable by anyone with `run.viewer`.
- **Least-privilege secret access:** each secret is readable only by the
  workloads that need it — `garda-jwt-secret`/`garda-ingest-token` → backend;
  `garda-scoring-token` → backend + scoring; `garda-database-url` → backend +
  jobs. The internal scoring SA can therefore neither forge JWTs nor read the DB.
- **Per-workload service accounts** (`garda-backend`, `garda-scoring`,
  `garda-frontend`, `garda-jobs`) receive only the roles they need
  (`cloudsql.client`, `secretmanager.secretAccessor`, `run.invoker`).

### Secret-in-state caveat (important)

The DB user password (`google_sql_user`), the Secret Manager secret versions, and
the interpolated `local.db_url` mean **Terraform state contains secret values**.
Never use a local state file for a real deployment: configure a **secured remote
backend** — e.g. a GCS bucket with restricted IAM, uniform bucket-level access,
and default encryption (optionally a CMEK). State is as sensitive as the secrets
themselves. For this reason `db_url` is only ever consumed internally and is
**not** exposed as an output.
