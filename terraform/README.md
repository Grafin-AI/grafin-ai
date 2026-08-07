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
4. **Apply:** `terraform apply`.
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

- **scoring** is `INGRESS_TRAFFIC_INTERNAL_ONLY` — never publicly reachable; the
  backend invokes it in-network with `roles/run.invoker` + a scoring token.
- **Cloud SQL + Memorystore are private** (`ipv4_enabled=false`, PSA + VPC
  connector, `egress = PRIVATE_RANGES_ONLY`). No public database endpoint.
- **Secrets** live in Secret Manager and are injected into the backend/scoring
  containers via `value_source.secret_key_ref` — never as plaintext env values.
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
