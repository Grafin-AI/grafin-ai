# GCP Cloud Run Deployment Runbook

**Date:** 2026-08-08
**Scope:** Operator checklist for deploying Garda AI to GCP Cloud Run.

## Prerequisites

- GCP project with billing enabled
- `gcloud` CLI installed and configured
- Docker installed (for local testing)
- Access to GitHub and the 4 service repos (`garda-ai-backend`, `garda-ai-dashboard-web`, `garda-ai-scoring`, `garda-ai-ingest`)

---

## Phase 1: GCP Project Setup

### Step 1.1: Create GCP Project & Enable Billing

```bash
gcloud projects create garda-ai-platform --name="Garda AI Platform"
gcloud config set project garda-ai-platform

# Link billing account
gcloud billing accounts list
gcloud billing projects link garda-ai-platform --billing-account=<YOUR_BILLING_ACCOUNT_ID>
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
gcloud projects add-iam-policy-binding garda-ai-platform \
  --member=serviceAccount:terraform-sa@garda-ai-platform.iam.gserviceaccount.com \
  --role=roles/editor   # For demo; use least-privilege in production

# Create and download key (only if not using Workload Identity)
# gcloud iam service-accounts keys create terraform-key.json \
#   --iam-account=terraform-sa@garda-ai-platform.iam.gserviceaccount.com
```

---

## Phase 2: Terraform Infrastructure

### Step 2.1: Prepare Terraform Variables and Environment

Navigate to `garda-ai-deploy/terraform/`:

```bash
cd garda-ai-deploy/terraform

# Set region and project (MUST match across all commands below)
export REGION="asia-southeast1"
export PROJECT="your-gcp-project"
export REGISTRY="${REGION}-docker.pkg.dev/${PROJECT}/garda"

# Copy the example tfvars
cp terraform.tfvars.example terraform.tfvars

# Edit terraform.tfvars with your values (these are the FULL image references):
cat > terraform.tfvars << 'EOF'
project_id = "your-gcp-project"
region     = "asia-southeast1"
domain     = ""
backend_image  = "asia-southeast1-docker.pkg.dev/your-gcp-project/garda/backend:latest"
frontend_image = "asia-southeast1-docker.pkg.dev/your-gcp-project/garda/frontend:latest"
scoring_image  = "asia-southeast1-docker.pkg.dev/your-gcp-project/garda/scoring:latest"
ingest_image   = "asia-southeast1-docker.pkg.dev/your-gcp-project/garda/ingest:latest"
EOF

# Secret values are supplied via environment variables (NOT committed to tfvars):
export TF_VAR_jwt_secret="<your-jwt-secret-32-chars-minimum>"
export TF_VAR_ingest_token="<your-ingest-token>"
export TF_VAR_scoring_token="<your-scoring-token>"
export TF_VAR_db_password="<postgres-password>"
```

**Important:** The four secrets are created by Terraform (not out-of-band). They are:
- `garda-jwt-secret` (JWT signing key)
- `garda-ingest-token` (bearer token for `/api/v1/ingest`)
- `garda-scoring-token` (bearer token for backend → scoring auth)
- Database password is used to create the Cloud SQL user; the actual DSN is stored as `garda-database-url` secret

### Step 2.2: Set Up Remote State Backend (Critical!)

Terraform state contains secrets and must be stored securely:

```bash
# Create a GCS bucket for remote state
gsutil mb -p ${PROJECT} -l ${REGION} gs://garda-ai-tf-state

# Enable versioning for disaster recovery
gsutil versioning set on gs://garda-ai-tf-state

# Create backend config
cat > backend.tf << 'EOF'
terraform {
  backend "gcs" {
    bucket = "garda-ai-tf-state"
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
cd ../garda-ai-backend

# Build and tag image
docker build -t ${REGISTRY}/backend:latest .

# Push image
docker push ${REGISTRY}/backend:latest

# Repeat for frontend, scoring, ingest (or trigger CI deploy.yml on push to main)
cd ../garda-ai-dashboard-web
docker build -t ${REGISTRY}/frontend:latest .
docker push ${REGISTRY}/frontend:latest

cd ../garda-ai-scoring
docker build -t ${REGISTRY}/scoring:latest .
docker push ${REGISTRY}/scoring:latest

cd ../garda-ai-ingest
docker build -t ${REGISTRY}/ingest:latest .
docker push ${REGISTRY}/ingest:latest
```

**Alternative:** Let CI/CD do the build and push:
- Push each service repo to `main` → deploy.yml triggers → images are built and pushed automatically to Artifact Registry

#### Phase 2.4.3: Deploy Services and Jobs

```bash
cd garda-ai-deploy/terraform

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
gcloud run jobs execute garda-migrate \
  --region=${REGION} \
  --wait

# 2. Load reference dataset (ingest seed)
gcloud run jobs execute garda-ingest \
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

For each service repo (`garda-ai-backend`, `garda-ai-dashboard-web`, `garda-ai-scoring`, `garda-ai-ingest`):

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
  --service=garda-frontend \
  --domain=app.garda.example.com \
  --region=${REGION}

# Map backend
gcloud run domain-mappings create \
  --service=garda-backend \
  --domain=api.garda.example.com \
  --region=${REGION}
```

### Step 5.2: Create DNS Records

Get the IP addresses from Terraform output:

```bash
terraform output domain_dns_frontend
terraform output domain_dns_backend
```

Add CNAME or A records to your DNS provider:
- `app.garda.example.com` → Cloud Run frontend IP
- `api.garda.example.com` → Cloud Run backend IP

Wait for DNS to propagate (typically 5-30 minutes):

```bash
# Test DNS resolution
nslookup app.garda.example.com
nslookup api.garda.example.com

# Test HTTPS (Google manages certs via Cloud Run)
curl -I https://app.garda.example.com
curl -I https://api.garda.example.com/healthz
```

---

## Phase 6: Verify Deployment

### Step 6.1: Check Service Status

```bash
export REGION="asia-southeast1"

gcloud run services list --region=${REGION}

gcloud run services describe garda-backend --region=${REGION}
gcloud run services describe garda-frontend --region=${REGION}
gcloud run services describe garda-scoring --region=${REGION}
```

### Step 6.2: Test Live Endpoints

```bash
# Backend health check
curl https://api.garda.example.com/healthz

# Frontend SPA
curl -I https://app.garda.example.com

# Backend ingest endpoint (requires valid token)
curl -X POST https://api.garda.example.com/api/v1/ingest \
  -H "Authorization: Bearer <INGEST_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"transactions": []}'
```

### Step 6.3: Monitor Logs

```bash
export REGION="asia-southeast1"

# Backend logs
gcloud run services logs read garda-backend --region=${REGION} --limit=50

# Scoring service logs
gcloud run services logs read garda-scoring --region=${REGION} --limit=50

# Ingest job execution logs
gcloud run jobs describe garda-ingest --region=${REGION}
```

---

## Phase 7: Local Simulation (Optional)

Test the deployed backend with the local simulator:

```bash
cd ../garda-ai-sim

# Set the deployed ingest URL and token
export GARDA_INGEST_URL=https://api.garda.example.com/api/v1/ingest
export GARDA_INGEST_TOKEN=<your-ingest-token>

# Run the simulator against the live backend
uv run garda-sim
```

Monitor the live feed in the dashboard at `https://app.garda.example.com`.

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
gcloud run revisions list --service=garda-backend --region=${REGION}

# Direct traffic to a previous revision
gcloud run services update-traffic garda-backend \
  --to-revisions=<PREVIOUS_REVISION_ID>=100 \
  --region=${REGION}
```

---

## Disaster Recovery

### State Backup

Terraform state is in GCS (`gs://garda-ai-tf-state`). GCS versioning is enabled for recovery.

### Database Backup

Cloud SQL automated backups are configured. To restore:

```bash
gcloud sql backups describe <BACKUP_ID> --instance=garda-postgres

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
