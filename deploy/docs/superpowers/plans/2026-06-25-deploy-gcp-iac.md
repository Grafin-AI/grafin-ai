# Deploy — GCP Cloud Run IaC (Phase 6 ②)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Prefer the `cloud-infrastructure` / `terraform-specialist` implementer. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Author Terraform under `grafin-ai-deploy/terraform/` that provisions the platform on **GCP Cloud Run**: 3 services (backend public, scoring internal, frontend public), 2 jobs (migrate, ingest), Cloud SQL (Postgres), Memorystore (Redis), a Serverless VPC Access connector, Secret Manager, Artifact Registry, and custom-domain mappings — with `deploy_observability` switchable.

**Architecture:** Cloud Run services reach the private Cloud SQL + Memorystore via a VPC connector. Secrets live in Secret Manager and are injected as env. Backend is public (`min_instances=1`, WS-friendly timeout); scoring is `internal` ingress (backend→scoring in-network, scoring-token enforced); frontend is public nginx. The `migrate` + `ingest` jobs run at deploy-init.

**Verification bar (no GCP creds here):** `terraform fmt -check`, `terraform init -backend=false`, and `terraform validate` pass. `terraform plan`/`apply` require the operator's GCP project + credentials and are the operator's step (documented in the runbook, plan ③/④).

**Spec:** `docs/superpowers/specs/2026-06-25-deploy-split-design.md`

**Note to implementer:** the HCL below is the intended shape; complete any provider-required arguments so `terraform validate` passes against the pinned `google` provider version. Keep resources in the per-concern files listed. Do NOT commit real secret values.

---

## File structure (all under `grafin-ai-deploy/terraform/`)

```
versions.tf      # terraform + google/google-beta provider pins
variables.tf     # inputs (project_id, region, domain, image tags, deploy_observability, sensitive secrets)
apis.tf          # google_project_service enablement
network.tf       # VPC, subnet, Serverless VPC Access connector, private services access (PSA) for Cloud SQL
registry.tf      # Artifact Registry docker repo
secrets.tf       # Secret Manager secrets + versions (from sensitive vars)
iam.tf           # service accounts (backend/scoring/frontend/jobs) + role bindings
database.tf      # Cloud SQL Postgres instance + database + user
redis.tf         # Memorystore Redis
cloudrun.tf      # 3 Cloud Run services (backend, scoring, frontend)
jobs.tf          # 2 Cloud Run Jobs (migrate, ingest)
domains.tf       # Cloud Run domain mappings (app./api.)
observability.tf # optional self-hosted prom+grafana, count = var.deploy_observability ? 1 : 0
outputs.tf       # service URLs, AR repo, DB connection name, DNS targets for domain mappings
terraform.tfvars.example
README.md        # how to init/validate; what the operator must do to apply
```

---

## Task 1: Providers, variables, API enablement

**Files:** Create `versions.tf`, `variables.tf`, `apis.tf`. Replace the placeholder `main.tf` (delete it).

- [ ] **Step 1: `versions.tf`**

```hcl
terraform {
  required_version = ">= 1.6"
  required_providers {
    google      = { source = "hashicorp/google", version = "~> 6.0" }
    google-beta = { source = "hashicorp/google-beta", version = "~> 6.0" }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}
```

- [ ] **Step 2: `variables.tf`**

```hcl
variable "project_id" { type = string }
variable "region"     { type = string, default = "asia-southeast1" }
variable "domain"     { type = string, default = "" } # e.g. grafin.example.com; "" disables domain mappings

variable "deploy_observability" { type = bool, default = false }

# Image references (pushed by per-repo CI to Artifact Registry). Default to :latest.
variable "backend_image"  { type = string }
variable "scoring_image"  { type = string }
variable "frontend_image" { type = string }
variable "ingest_image"   { type = string }

variable "db_tier"    { type = string, default = "db-custom-1-3840" }
variable "redis_tier" { type = string, default = "BASIC" }
variable "redis_size_gb" { type = number, default = 1 }

# Secrets (provided out-of-band; never commit real values). Marked sensitive.
variable "jwt_secret"    { type = string, sensitive = true }
variable "ingest_token"  { type = string, sensitive = true }
variable "scoring_token" { type = string, sensitive = true }
variable "db_password"   { type = string, sensitive = true }
```

- [ ] **Step 3: `apis.tf`**

```hcl
locals {
  services = [
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "redis.googleapis.com",
    "vpcaccess.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "servicenetworking.googleapis.com",
    "compute.googleapis.com",
  ]
}

resource "google_project_service" "enabled" {
  for_each                   = toset(local.services)
  service                    = each.value
  disable_dependent_services = false
  disable_on_destroy         = false
}
```

- [ ] **Step 4: Init + validate**

Run: `cd grafin-ai-deploy/terraform && rm -f main.tf README.md && terraform fmt && terraform init -backend=false && terraform validate`
Expected: `Success! The configuration is valid.` (validate does not contact GCP.)

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(iac): GCP providers, variables, API enablement"
```

---

## Task 2: Network, registry, secrets, IAM

**Files:** Create `network.tf`, `registry.tf`, `secrets.tf`, `iam.tf`.

- [ ] **Step 1: `network.tf` — VPC + connector + private services access**

```hcl
resource "google_compute_network" "vpc" {
  name                    = "grafin-vpc"
  auto_create_subnetworks = false
  depends_on              = [google_project_service.enabled]
}

resource "google_compute_subnetwork" "subnet" {
  name          = "grafin-subnet"
  ip_cidr_range = "10.10.0.0/24"
  region        = var.region
  network       = google_compute_network.vpc.id
}

resource "google_vpc_access_connector" "connector" {
  name          = "grafin-vpc-conn"
  region        = var.region
  network       = google_compute_network.vpc.name
  ip_cidr_range = "10.8.0.0/28"
  depends_on    = [google_project_service.enabled]
}

# Private Services Access range for Cloud SQL private IP
resource "google_compute_global_address" "psa_range" {
  name          = "grafin-psa"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.vpc.id
}

resource "google_service_networking_connection" "psa" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.psa_range.name]
}
```

- [ ] **Step 2: `registry.tf`**

```hcl
resource "google_artifact_registry_repository" "docker" {
  location      = var.region
  repository_id = "grafin"
  format        = "DOCKER"
  depends_on    = [google_project_service.enabled]
}
```

- [ ] **Step 3: `secrets.tf` — Secret Manager secrets + versions**

```hcl
locals {
  secrets = {
    "grafin-jwt-secret"    = var.jwt_secret
    "grafin-ingest-token"  = var.ingest_token
    "grafin-scoring-token" = var.scoring_token
    "grafin-db-password"   = var.db_password
  }
}

resource "google_secret_manager_secret" "s" {
  for_each  = local.secrets
  secret_id = each.key
  replication { auto {} }
  depends_on = [google_project_service.enabled]
}

resource "google_secret_manager_secret_version" "v" {
  for_each    = local.secrets
  secret      = google_secret_manager_secret.s[each.key].id
  secret_data = each.value
}
```

- [ ] **Step 4: `iam.tf` — one service account per workload + least-privilege roles**

```hcl
resource "google_service_account" "backend" { account_id = "grafin-backend" }
resource "google_service_account" "scoring" { account_id = "grafin-scoring" }
resource "google_service_account" "frontend" { account_id = "grafin-frontend" }
resource "google_service_account" "jobs" { account_id = "grafin-jobs" }

# Backend + jobs need Cloud SQL client + secret access
resource "google_project_iam_member" "backend_sql" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.backend.email}"
}
resource "google_project_iam_member" "jobs_sql" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.jobs.email}"
}

# Secret accessor for the SAs that consume secrets (backend, scoring, jobs)
resource "google_secret_manager_secret_iam_member" "access" {
  for_each  = { for pair in setproduct(keys(local.secrets), ["backend", "scoring", "jobs"]) : "${pair[0]}-${pair[1]}" => pair }
  secret_id = google_secret_manager_secret.s[each.value[0]].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account[each.value[1]].email}"
}

# Backend may invoke the internal scoring service (service-to-service auth)
resource "google_cloud_run_v2_service_iam_member" "backend_invokes_scoring" {
  name     = google_cloud_run_v2_service.scoring.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.backend.email}"
}
```

> Implementer note: `google_service_account[each.value[1]]` cannot index a resource by string directly — use a `locals` map `{ backend = google_service_account.backend.email, ... }` and index that. Adjust so `terraform validate` passes.

- [ ] **Step 5: fmt + validate + commit**

Run: `terraform fmt && terraform validate`
```bash
git add -A && git commit -m "feat(iac): VPC + connector + PSA, Artifact Registry, Secret Manager, IAM"
```

---

## Task 3: Cloud SQL + Memorystore

**Files:** Create `database.tf`, `redis.tf`.

- [ ] **Step 1: `database.tf`**

```hcl
resource "google_sql_database_instance" "pg" {
  name             = "grafin-pg"
  database_version = "POSTGRES_16"
  region           = var.region
  depends_on       = [google_service_networking_connection.psa]

  settings {
    tier = var.db_tier
    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.vpc.id
    }
  }
  deletion_protection = false
}

resource "google_sql_database" "db" {
  name     = "grafin"
  instance = google_sql_database_instance.pg.name
}

resource "google_sql_user" "user" {
  name     = "grafin"
  instance = google_sql_database_instance.pg.name
  password = var.db_password
}
```

- [ ] **Step 2: `redis.tf`**

```hcl
resource "google_redis_instance" "redis" {
  name               = "grafin-redis"
  tier               = var.redis_tier
  memory_size_gb     = var.redis_size_gb
  region             = var.region
  authorized_network = google_compute_network.vpc.id
  connect_mode       = "PRIVATE_SERVICE_ACCESS"
  depends_on         = [google_service_networking_connection.psa]
}
```

- [ ] **Step 3: fmt + validate + commit**

```bash
terraform fmt && terraform validate
git add -A && git commit -m "feat(iac): Cloud SQL Postgres + Memorystore Redis (private)"
```

---

## Task 4: Cloud Run services + jobs

**Files:** Create `cloudrun.tf`, `jobs.tf`. Build the connection strings as `locals`.

- [ ] **Step 1: `locals` for connection strings** (put at the top of `cloudrun.tf`)

```hcl
locals {
  db_url = "postgresql+asyncpg://grafin:${var.db_password}@${google_sql_database_instance.pg.private_ip_address}:5432/grafin"
  redis_url = "redis://${google_redis_instance.redis.host}:${google_redis_instance.redis.port}/0"
}
```
> Implementer note: prefer injecting the DB password via a Secret Manager env ref rather than interpolating it into `db_url`. If keeping the URL as a local for simplicity, mark any output using it as sensitive and never output it. Document the trade-off in `README.md`.

- [ ] **Step 2: `cloudrun.tf` — scoring (internal), backend (public), frontend (public)**

```hcl
resource "google_cloud_run_v2_service" "scoring" {
  name     = "grafin-scoring"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  template {
    service_account = google_service_account.scoring.email
    vpc_access {
      connector = google_vpc_access_connector.connector.id
      egress    = "PRIVATE_RANGES_ONLY"
    }
    containers {
      image = var.scoring_image
      ports { container_port = 8000 }
      env {
        name = "GRAFIN_SCORING_TOKEN"
        value_source { secret_key_ref { secret = google_secret_manager_secret.s["grafin-scoring-token"].secret_id, version = "latest" } }
      }
    }
  }
}

resource "google_cloud_run_v2_service" "backend" {
  name     = "grafin-backend"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.backend.email
    scaling { min_instance_count = 1 }   # keep the WS relay + Redis subscription warm
    vpc_access {
      connector = google_vpc_access_connector.connector.id
      egress    = "PRIVATE_RANGES_ONLY"
    }
    containers {
      image = var.backend_image
      ports { container_port = 8000 }
      env {
        name  = "GRAFIN_DATABASE_URL"
        value = local.db_url
      }
      env {
        name  = "GRAFIN_REDIS_URL"
        value = local.redis_url
      }
      env {
        name  = "GRAFIN_SCORING_URL"
        value = google_cloud_run_v2_service.scoring.uri
      }
      env {
        name = "GRAFIN_JWT_SECRET"
        value_source { secret_key_ref { secret = google_secret_manager_secret.s["grafin-jwt-secret"].secret_id, version = "latest" } }
      }
      env {
        name = "GRAFIN_INGEST_TOKEN"
        value_source { secret_key_ref { secret = google_secret_manager_secret.s["grafin-ingest-token"].secret_id, version = "latest" } }
      }
      env {
        name = "GRAFIN_SCORING_TOKEN"
        value_source { secret_key_ref { secret = google_secret_manager_secret.s["grafin-scoring-token"].secret_id, version = "latest" } }
      }
    }
    # WebSocket relay: allow long-lived requests
    timeout = "3600s"
  }
}

# Backend is public: allow unauthenticated (app enforces JWT/ingest-token itself)
resource "google_cloud_run_v2_service_iam_member" "backend_public" {
  name     = google_cloud_run_v2_service.backend.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service" "frontend" {
  name     = "grafin-frontend"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.frontend.email
    containers {
      image = var.frontend_image
      ports { container_port = 8080 }
      env {
        name  = "BACKEND_URL"     # consumed by the templated nginx.conf (plan ③)
        value = google_cloud_run_v2_service.backend.uri
      }
    }
  }
}

resource "google_cloud_run_v2_service_iam_member" "frontend_public" {
  name     = google_cloud_run_v2_service.frontend.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}
```

- [ ] **Step 3: `jobs.tf` — migrate + ingest**

```hcl
resource "google_cloud_run_v2_job" "migrate" {
  name     = "grafin-migrate"
  location = var.region
  template {
    template {
      service_account = google_service_account.jobs.email
      vpc_access {
        connector = google_vpc_access_connector.connector.id
        egress    = "PRIVATE_RANGES_ONLY"
      }
      containers {
        image   = var.backend_image
        command = ["uv", "run", "alembic", "upgrade", "head"]
        env {
          name  = "GRAFIN_DATABASE_URL"
          value = local.db_url
        }
      }
    }
  }
}

resource "google_cloud_run_v2_job" "ingest" {
  name     = "grafin-ingest"
  location = var.region
  template {
    template {
      service_account = google_service_account.jobs.email
      vpc_access {
        connector = google_vpc_access_connector.connector.id
        egress    = "PRIVATE_RANGES_ONLY"
      }
      containers {
        image = var.ingest_image
        env {
          name  = "GRAFIN_DATABASE_URL"
          value = local.db_url
        }
        # The reference CSV is baked into the ingest image (simplest for the demo).
        # GRAFIN_DATA_DIR defaults to the image's bundled data path.
      }
    }
  }
}
```
> Implementer note: confirm the ingest image bundles the reference CSV (or add a GCS mount). Document in `README.md`. The backend Cloud Run service also self-migrates via its entrypoint; the `migrate` job exists for an explicit, ordered deploy-init step (run it before first traffic). Note the redundancy is harmless (alembic is idempotent).

- [ ] **Step 4: fmt + validate + commit**

```bash
terraform fmt && terraform validate
git add -A && git commit -m "feat(iac): Cloud Run services (backend/scoring/frontend) + migrate/ingest jobs"
```

---

## Task 5: Domain mappings, observability toggle, outputs, tfvars example

**Files:** Create `domains.tf`, `observability.tf`, `outputs.tf`, `terraform.tfvars.example`, `README.md`.

- [ ] **Step 1: `domains.tf` (only when `var.domain != ""`)**

```hcl
resource "google_cloud_run_domain_mapping" "app" {
  count    = var.domain == "" ? 0 : 1
  name     = "app.${var.domain}"
  location = var.region
  metadata { namespace = var.project_id }
  spec { route_name = google_cloud_run_v2_service.frontend.name }
}

resource "google_cloud_run_domain_mapping" "api" {
  count    = var.domain == "" ? 0 : 1
  name     = "api.${var.domain}"
  location = var.region
  metadata { namespace = var.project_id }
  spec { route_name = google_cloud_run_v2_service.backend.name }
}
```

- [ ] **Step 2: `observability.tf` — gated module/resources**

```hcl
# Switchable: when false, rely on Cloud Monitoring / Google Managed Prometheus.
# When true, provision a minimal self-hosted Prometheus + Grafana.
# Kept as a clean on/off boundary; the leanest GCP-native shape is left to the
# implementer (e.g. a small GCE e2-micro running both, scraping backend/scoring /metrics).
locals {
  observability_enabled = var.deploy_observability
}

# Example gate (implementer completes the chosen shape):
# resource "google_compute_instance" "observability" {
#   count = local.observability_enabled ? 1 : 0
#   ...
# }
```
> Implementer: implement a minimal working self-hosted stack behind `count = local.observability_enabled ? 1 : 0`, OR wire Google Managed Prometheus scraping. Whatever you choose must `terraform validate`. Default (`false`) provisions nothing.

- [ ] **Step 3: `outputs.tf`**

```hcl
output "backend_url"     { value = google_cloud_run_v2_service.backend.uri }
output "frontend_url"    { value = google_cloud_run_v2_service.frontend.uri }
output "scoring_url"     { value = google_cloud_run_v2_service.scoring.uri }
output "artifact_repo"   { value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.docker.repository_id}" }
output "db_connection"   { value = google_sql_database_instance.pg.connection_name }
output "domain_dns_app"  { value = try(google_cloud_run_domain_mapping.app[0].status[0].resource_records, []) }
output "domain_dns_api"  { value = try(google_cloud_run_domain_mapping.api[0].status[0].resource_records, []) }
```

- [ ] **Step 4: `terraform.tfvars.example`**

```hcl
project_id = "your-gcp-project"
region     = "asia-southeast1"
domain     = "" # e.g. "grafin.example.com" to enable app./api. mappings

deploy_observability = false

backend_image  = "asia-southeast1-docker.pkg.dev/your-gcp-project/grafin/backend:latest"
scoring_image  = "asia-southeast1-docker.pkg.dev/your-gcp-project/grafin/scoring:latest"
frontend_image = "asia-southeast1-docker.pkg.dev/your-gcp-project/grafin/frontend:latest"
ingest_image   = "asia-southeast1-docker.pkg.dev/your-gcp-project/grafin/ingest:latest"

# Secrets — provide via a *.auto.tfvars that is gitignored, or -var / TF_VAR_ env, NEVER commit real values.
jwt_secret    = "CHANGE-ME-32+chars"
ingest_token  = "CHANGE-ME-16+chars"
scoring_token = "CHANGE-ME"
db_password   = "CHANGE-ME"
```

- [ ] **Step 5: `README.md` (terraform)** — document: `terraform init`/`validate` (no creds), and the operator apply path (auth to GCP, provide secrets via env/`*.auto.tfvars`, `terraform apply`, then run the `migrate` + `ingest` jobs, then the services serve). Note the secret-in-state caveat (Terraform state contains secret values → use a secured remote backend, e.g. a GCS bucket with restricted access).

- [ ] **Step 6: Ensure `terraform/.gitignore` excludes state + secret tfvars**

Add/confirm `grafin-ai-deploy/terraform/.gitignore`:
```
.terraform/
*.tfstate
*.tfstate.*
*.auto.tfvars
crash.log
```

- [ ] **Step 7: Final fmt + validate + commit**

Run: `cd grafin-ai-deploy/terraform && terraform fmt -check && terraform init -backend=false && terraform validate`
Expected: `Success! The configuration is valid.`
```bash
git add -A && git commit -m "feat(iac): domain mappings, observability toggle, outputs, tfvars example + gitignore"
```

---

## Definition of Done

- `terraform fmt -check` clean; `terraform init -backend=false` + `terraform validate` succeed.
- Backend = public + `min_instances=1` + WS timeout; scoring = `INGRESS_TRAFFIC_INTERNAL_ONLY`; frontend = public with `BACKEND_URL` env.
- Cloud SQL + Memorystore are private (via VPC connector + PSA); secrets are in Secret Manager (no plaintext in committed files); per-workload service accounts with least-privilege roles.
- `migrate` + `ingest` Cloud Run Jobs defined; domain mappings gated on `var.domain`; `deploy_observability` gates the observability resources (default off → nothing).
- `terraform/.gitignore` excludes state + secret tfvars; README documents the operator apply path + secret-in-state caveat.
- All commits authored as Thariq with the `Co-Authored-By: Claude` trailer.

## Out of scope (operator's step)

`terraform plan`/`apply` (needs the GCP project + credentials + billing), Workload Identity Federation setup, DNS record creation for the domain mappings, and remote-state backend provisioning. All documented in the plan-④ runbook.
```
