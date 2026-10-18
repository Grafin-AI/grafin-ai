# GCP Cloud Run Deployment Runbook

**Date:** 2026-08-08
**Scope:** Operator checklist for deploying Grafin AI to GCP Cloud Run.

## Prerequisites

- GCP project with billing enabled
- `gcloud` CLI installed and configured
- Docker installed (for local testing)
- Access to GitHub and the 4 service repos (`grafin-ai-backend`, `grafin-ai-dashboard-web`, `grafin-ai-scoring`, `grafin-ai-ingest`)

---

## Deploy Sequence

**Deploys are always a deliberate operator action — nothing deploys on a merge to `main`.**

**Cold start (first time, once):**

1. **Foundation:** `terraform apply -target=...` (VPC, Cloud SQL, Redis, Artifact Registry, secrets) — Phase 2.4.1.
2. **Seed first images:** in each service repo, `make push` (build + push only — does NOT create the service) — Phase 2.4.2.
3. **Create services/jobs:** full `terraform apply` — images now exist, so services get created with their VPC / secret / ingress wiring — Phase 2.4.3.
4. **Init data:** `gcloud run jobs execute grafin-migrate --region $REGION --wait`, then in `grafin-ai-ingest` run `make execute` (seeds reference data) — Phase 3.

**Routine redeploy (the common case):**

- In the changed service repo: `make deploy` (build → push → `gcloud run deploy` a new revision). No terraform, no other services touched.
- Or: GitHub Actions tab → **deploy** → **Run workflow** (`workflow_dispatch`).
- Breaking DB migration: run the `grafin-migrate` job first. Because the migrate job stays terraform-owned, refresh it with `terraform apply` (re-resolves the backend `:latest` digest) before `gcloud run jobs execute grafin-migrate --wait`.

**Division of labor:** `terraform` owns resource creation and wiring; `make deploy` owns image rollout. The terraform `lifecycle { ignore_changes = [...image] }` on the three services and the ingest job keeps `terraform apply` from reverting an operator's rollout.

---

## Phase 1: GCP Project Setup

### Step 1.1: Create GCP Project & Enable Billing

```bash
gcloud projects create grafin-ai-platform --name="Grafin AI Platform"
gcloud config set project grafin-ai-platform

# Link billing account
gcloud billing accounts list
gcloud billing projects link grafin-ai-platform --billing-account=<YOUR_BILLING_ACCOUNT_ID>
```

### Step 1.2: Enable Required APIs

```bash
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  redis.googleapis.com \
  vpcaccess.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  compute.googleapis.com \
  cloudresourcemanager.googleapis.com
```

### Step 1.3: Set Up Service Accounts for GCP Infrastructure

Create a Terraform service account with deployment permissions:

```bash
# Create service account
gcloud iam service-accounts create terraform-sa \
  --display-name="Terraform Deployment Account"

# Grant required roles
gcloud projects add-iam-policy-binding grafin-ai-platform \
  --member=serviceAccount:terraform-sa@grafin-ai-platform.iam.gserviceaccount.com \
  --role=roles/editor   # For demo; use least-privilege in production

# Create and download key (only if not using Workload Identity)
# gcloud iam service-accounts keys create terraform-key.json \
#   --iam-account=terraform-sa@grafin-ai-platform.iam.gserviceaccount.com
```

---

## Phase 2: Terraform Infrastructure

### Step 2.1: Prepare Terraform Variables and Environment

Navigate to `grafin-ai-deploy/terraform/`:

```bash
cd grafin-ai-deploy/terraform

# Set region and project (MUST match across all commands below)
export REGION="asia-southeast1"
export PROJECT="your-gcp-project"
export REGISTRY="${REGION}-docker.pkg.dev/${PROJECT}/grafin"

# Copy the example tfvars
cp terraform.tfvars.example terraform.tfvars

# Edit terraform.tfvars with your values (these are the FULL image references):
cat > terraform.tfvars << 'EOF'
project_id = "your-gcp-project"
region     = "asia-southeast1"
domain     = ""
backend_image  = "asia-southeast1-docker.pkg.dev/your-gcp-project/grafin/backend:latest"
frontend_image = "asia-southeast1-docker.pkg.dev/your-gcp-project/grafin/frontend:latest"
scoring_image  = "asia-southeast1-docker.pkg.dev/your-gcp-project/grafin/scoring:latest"
ingest_image   = "asia-southeast1-docker.pkg.dev/your-gcp-project/grafin/ingest:latest"
EOF

# Secret values are supplied via environment variables (NOT committed to tfvars):
export TF_VAR_jwt_secret="<your-jwt-secret-32-chars-minimum>"
export TF_VAR_ingest_token="<your-ingest-token>"
export TF_VAR_scoring_token="<your-scoring-token>"
export TF_VAR_db_password="<postgres-password>"
```

**Important:** The four secrets are created by Terraform (not out-of-band). They are:
- `grafin-jwt-secret` (JWT signing key)
- `grafin-ingest-token` (bearer token for `/api/v1/ingest`)
- `grafin-scoring-token` (bearer token for backend → scoring auth)
- Database password is used to create the Cloud SQL user; the actual DSN is stored as `grafin-database-url` secret

### Step 2.2: Set Up Remote State Backend (Critical!)

Terraform state contains secrets and must be stored securely:

```bash
# Create a GCS bucket for remote state
gsutil mb -p ${PROJECT} -l ${REGION} gs://grafin-ai-tf-state

# Enable versioning for disaster recovery
gsutil versioning set on gs://grafin-ai-tf-state

# Create backend config
cat > backend.tf << 'EOF'
terraform {
  backend "gcs" {
    bucket = "grafin-ai-tf-state"
    prefix = "terraform/state"
  }
}
EOF

# Initialize backend
terraform init
```

### Step 2.3: Validate

```bash
# Validate syntax
terraform validate
```

### Step 2.4: Two-Phase Apply (Critical for Cloud Run Image Validation)

**Why two phases?** Cloud Run services validate that images exist at deployment time. We must push images BEFORE creating the services.

**Phase 1 → Phase 2 → Phase 3:**
1. **Phase 1:** Provision infrastructure (VPC, Cloud SQL, Memorystore, Artifact Registry, secrets)
2. **Phase 2:** Build and push all 4 images to Artifact Registry
3. **Phase 3:** Deploy services and jobs (now that images exist)

#### Phase 2.4.1: Provision Infrastructure

```bash
# Apply infrastructure targets ONLY (no Cloud Run services/jobs yet).
# Do NOT use a saved plan file with -target (Terraform rejects this).
terraform apply \
  -target=google_project_service.enabled \
  -target=google_artifact_registry_repository.docker \
  -target=google_compute_network.vpc \
  -target=google_compute_subnetwork.subnet \
  -target=google_vpc_access_connector.connector \
  -target=google_service_networking_connection.psa \
  -target=google_sql_database_instance.pg \
  -target=google_sql_database.db \
  -target=google_sql_user.user \
  -target=google_redis_instance.redis \
  -target=google_secret_manager_secret.s \
  -target=google_secret_manager_secret_version.v
```

**Note:** Secrets are created by Terraform from the `TF_VAR_*` environment variables. Do NOT use `gcloud secrets versions add` out-of-band (the Terraform-managed versions will take precedence).

#### Phase 2.4.2: Build and Push Images

Configure Docker for Artifact Registry and build images in each service repo:

```bash
# Authenticate Docker to Artifact Registry
gcloud auth configure-docker ${REGION}-docker.pkg.dev

# For each service repo (backend, frontend, scoring, ingest):
cd ../grafin-ai-backend

# Build and tag image
docker build -t ${REGISTRY}/backend:latest .

# Push image
docker push ${REGISTRY}/backend:latest

# Repeat for frontend, scoring, ingest (or use `make push` in each repo)
cd ../grafin-ai-dashboard-web
docker build -t ${REGISTRY}/frontend:latest .
docker push ${REGISTRY}/frontend:latest

cd ../grafin-ai-scoring
docker build -t ${REGISTRY}/scoring:latest .
docker push ${REGISTRY}/scoring:latest

cd ../grafin-ai-ingest
docker build -t ${REGISTRY}/ingest:latest .
docker push ${REGISTRY}/ingest:latest
```

**Deploying a service (two equivalent manual routes — neither auto-fires):**

1. **Local (operator clones the repo):**
   ```bash
   cd grafin-ai-<service>
   cp deploy.env.example deploy.env   # edit GCP_PROJECT / GCP_REGION (or export them)
   make deploy                        # build -> push -> gcloud run deploy
   ```
   Uses your own `gcloud auth login`. For the ingest job: `make deploy` then `make execute`.

2. **GitHub button:** Actions tab → **deploy** → **Run workflow** (`workflow_dispatch`).
   Requires the Workload Identity Federation setup (Phase 4). Never triggers on a merge to `main`.

**Note:** during cold start use `make push` (build + push only). The Cloud Run services do not exist yet
at that point — terraform creates them in Phase 2.4.3. Use `make deploy` for routine redeploys afterwards.

#### Phase 2.4.3: Deploy Services and Jobs

```bash
cd grafin-ai-deploy/terraform

# Now apply the FULL Terraform (services, jobs, domain mappings, etc.)
# All images exist, so Cloud Run validation will pass.
terraform apply
```

---

## Phase 3: Deploy-Init Jobs

Before services take traffic, run the initialization jobs in order:

```bash
# Set region for all gcloud commands
export REGION="asia-southeast1"

# 1. Run database migrations
gcloud run jobs execute grafin-migrate \
  --region=${REGION} \
  --wait

# 2. Load reference dataset (ingest seed)
gcloud run jobs execute grafin-ingest \
  --region=${REGION} \
  --wait
```

---

## Phase 4: Set Up Workload Identity Federation (CI/CD Authentication)

Each service repo needs GitHub Actions to authenticate to GCP with short-lived credentials (no long-lived API keys).

### Step 4.1: Create Workload Identity Provider

```bash
export PROJECT="your-gcp-project"

# Create the provider
gcloud iam workload-identity-pools create "github-pool" \
  --project=${PROJECT} \
  --location=global \
  --display-name="GitHub Actions"

# Create OIDC provider configuration
gcloud iam workload-identity-providers create-oidc "github-provider" \
  --project=${PROJECT} \
  --location=global \
  --display-name="GitHub" \
  --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner" \
  --issuer-uri=https://token.actions.githubusercontent.com \
  --attribute-condition="assertion.repository_owner == 'your-org'"
```

### Step 4.2: Create Service Account for CI/CD Deployments

```bash
# Create service account
gcloud iam service-accounts create github-deployer \
  --project=${PROJECT} \
  --display-name="GitHub Actions Deployer"

# Grant Cloud Run deployment permissions
gcloud projects add-iam-policy-binding ${PROJECT} \
  --member=serviceAccount:github-deployer@${PROJECT}.iam.gserviceaccount.com \
  --role=roles/run.admin

# Grant Artifact Registry push permissions
gcloud projects add-iam-policy-binding ${PROJECT} \
  --member=serviceAccount:github-deployer@${PROJECT}.iam.gserviceaccount.com \
  --role=roles/artifactregistry.writer

# Allow GitHub to impersonate the service account
gcloud iam service-accounts add-iam-policy-binding \
  github-deployer@${PROJECT}.iam.gserviceaccount.com \
  --project=${PROJECT} \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT}/locations/global/workloadIdentityPools/github-pool/attribute.repository/your-org/repo-name"
```

### Step 4.3: Set Repository Secrets and Variables

For each service repo (`grafin-ai-backend`, `grafin-ai-dashboard-web`, `grafin-ai-scoring`, `grafin-ai-ingest`):

**Repository Variables** (Settings → Secrets and variables → Variables):
- `GCP_PROJECT`: `your-gcp-project`
- `GCP_REGION`: `asia-southeast1`

**Repository Secrets** (Settings → Secrets and variables → Secrets):
- `GCP_WIF_PROVIDER`: The Workload Identity Provider resource name (from step 4.1 output)
- `GCP_DEPLOYER_SA`: `github-deployer@your-gcp-project.iam.gserviceaccount.com`

Example WIF Provider name: `projects/123456/locations/global/workloadIdentityPools/github-pool/providers/github-provider`

---

## Phase 5: Domain & DNS

### Step 5.1: Create Cloud Run Domain Mappings

```bash
export REGION="asia-southeast1"

# Map frontend
gcloud run domain-mappings create \
  --service=grafin-frontend \
  --domain=app.grafin.example.com \
  --region=${REGION}

# Map backend
gcloud run domain-mappings create \
  --service=grafin-backend \
  --domain=api.grafin.example.com \
  --region=${REGION}
```

### Step 5.2: Create DNS Records

Get the IP addresses from Terraform output:

```bash
terraform output domain_dns_frontend
terraform output domain_dns_backend
```

Add CNAME or A records to your DNS provider:
- `app.grafin.example.com` → Cloud Run frontend IP
- `api.grafin.example.com` → Cloud Run backend IP

Wait for DNS to propagate (typically 5-30 minutes):

```bash
# Test DNS resolution
nslookup app.grafin.example.com
nslookup api.grafin.example.com

# Test HTTPS (Google manages certs via Cloud Run)
curl -I https://app.grafin.example.com
curl -I https://api.grafin.example.com/healthz
```

---

## Phase 6: Verify Deployment

### Step 6.1: Check Service Status

```bash
export REGION="asia-southeast1"

gcloud run services list --region=${REGION}

gcloud run services describe grafin-backend --region=${REGION}
gcloud run services describe grafin-frontend --region=${REGION}
gcloud run services describe grafin-scoring --region=${REGION}
```

### Step 6.2: Test Live Endpoints

```bash
# Backend health check
curl https://api.grafin.example.com/healthz

# Frontend SPA
curl -I https://app.grafin.example.com

# Backend ingest endpoint (requires valid token)
curl -X POST https://api.grafin.example.com/api/v1/ingest \
  -H "Authorization: Bearer <INGEST_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"transactions": []}'
```

### Step 6.3: Monitor Logs

```bash
export REGION="asia-southeast1"

# Backend logs
gcloud run services logs read grafin-backend --region=${REGION} --limit=50

# Scoring service logs
gcloud run services logs read grafin-scoring --region=${REGION} --limit=50

# Ingest job execution logs
gcloud run jobs describe grafin-ingest --region=${REGION}
```

---

## Phase 7: Local Simulation (Optional)

Test the deployed backend with the local simulator:

```bash
cd ../grafin-ai-sim

# Set the deployed ingest URL and token
export GRAFIN_INGEST_URL=https://api.grafin.example.com/api/v1/ingest
export GRAFIN_INGEST_TOKEN=<your-ingest-token>

# Run the simulator against the live backend
uv run grafin-sim
```

Monitor the live feed in the dashboard at `https://app.grafin.example.com`.

---

## Phase 8: Monitoring & Maintenance

### Cloud Monitoring (Built-in)

Google Cloud provides free monitoring via Cloud Monitoring. View dashboards:

```bash
gcloud monitoring dashboards list
```

### Optional: Self-Hosted Prometheus + Grafana

If you set `deploy_observability = true` in Terraform:

```bash
# Get Grafana URL
terraform output grafana_url

# Prometheus scrapes /metrics from backend and scoring services
```

---

## Troubleshooting

### Images Not Found at Deploy Time

**Problem:** `terraform apply` fails with "image not found in Artifact Registry"

**Solution:** Ensure images are pushed (Phase 2.4.2) before running the full `terraform apply` (Phase 2.4.3).

### Database Connection Timeouts

**Problem:** Backend fails to connect to Cloud SQL

**Solution:**
1. Verify VPC connector is attached to Cloud Run services
2. Check Cloud SQL private IP is in the same VPC
3. Verify Cloud SQL has the correct database and user
4. Check `TF_VAR_db_password` was set correctly during `terraform apply`

### Secret Access Denied

**Problem:** Services fail to access Secret Manager

**Solution:**
1. Verify service account has `roles/secretmanager.secretAccessor`
2. Check Terraform created the secrets (Phase 2.4.1 created the secret resources and versions from `TF_VAR_*`)
3. Review IAM policy for the service account

### Scoring Service Connection Refused

**Problem:** Backend cannot reach scoring service

**Solution:**
1. Verify scoring service has `roles/run.invoker` granted to backend service account
2. Check scoring service ingress is set to internal-only
3. Verify both services are in the same VPC connector

---

## Rollback

To rollback a deployment:

```bash
export REGION="asia-southeast1"

# List Cloud Run service revisions
gcloud run revisions list --service=grafin-backend --region=${REGION}

# Direct traffic to a previous revision
gcloud run services update-traffic grafin-backend \
  --to-revisions=<PREVIOUS_REVISION_ID>=100 \
  --region=${REGION}
```

---

## Disaster Recovery

### State Backup

Terraform state is in GCS (`gs://grafin-ai-tf-state`). GCS versioning is enabled for recovery.

### Database Backup

Cloud SQL automated backups are configured. To restore:

```bash
gcloud sql backups describe <BACKUP_ID> --instance=grafin-postgres

# Create new instance from backup (manual process)
```

---

## Next Steps

1. **Scaling:** Adjust Cloud Run service `min_instances` and `max_instances` based on traffic
2. **Observability:** Enable Cloud Logging and Cloud Trace integration
3. **Custom Domain & WAF:** Use Cloud Armor for additional security
4. **Cost Optimization:** Review and tune instance sizes, reserved capacity
5. **Disaster Recovery:** Plan multi-region failover strategy

---

**For detailed architecture, see:** `docs/c4/02-container.md`
**For local development, see:** `README.md`
