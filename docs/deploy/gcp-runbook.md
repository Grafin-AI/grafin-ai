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

### Step 2.1: Prepare Terraform Variables

Navigate to `garda-ai-deploy/terraform/`:

```bash
cd garda-ai-deploy/terraform

# Copy the example tfvars
cp terraform.tfvars.example terraform.tfvars

# Edit terraform.tfvars with your values:
#   - project_id: your GCP project ID
#   - region: desired region (e.g., us-central1)
#   - domain: your custom domain (e.g., garda.example.com)
#   - deploy_observability: true/false (self-hosted Prometheus/Grafana)
#   - image_tags: backend, frontend, scoring, ingest image tags (e.g., latest)

# Example:
cat > terraform.tfvars << 'EOF'
project_id            = "garda-ai-platform"
region                = "us-central1"
domain                = "garda.example.com"
deploy_observability  = false
backend_image_tag     = "latest"
frontend_image_tag    = "latest"
scoring_image_tag     = "latest"
ingest_image_tag      = "latest"
EOF
```

### Step 2.2: Set Up Remote State Backend (Critical!)

Terraform state contains secrets and must be stored securely:

```bash
# Create a GCS bucket for remote state
gsutil mb -p garda-ai-platform -l us-central1 gs://garda-ai-tf-state

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

### Step 2.3: Validate and Plan

```bash
# Validate syntax
terraform validate

# Generate plan
terraform plan -out=tfplan

# Review the plan carefully before proceeding
```

### Step 2.4: Two-Phase Apply (Critical for Cloud Run Image Validation)

**Why two phases?** Cloud Run services validate that images exist at deployment time. We must push images before creating the services.

#### Phase 2.4a: Provision Infrastructure (Network, DB, Registry, Secrets)

```bash
# Apply only the prerequisites: VPC, Cloud SQL, Memorystore, Artifact Registry, Secret Manager
terraform apply -target=google_artifact_registry_repository.garda \
  -target=google_compute_network.vpc \
  -target=google_vpc_access_connector.connector \
  -target=google_sql_database_instance.postgres \
  -target=google_sql_database.garda \
  -target=google_sql_user.garda \
  -target=google_redis_instance.redis \
  -target=google_secret_manager_secret.jwt_secret \
  -target=google_secret_manager_secret.ingest_token \
  -target=google_secret_manager_secret.scoring_token \
  -target=google_secret_manager_secret.db_password \
  tfplan
```

#### Phase 2.4b: Set Secret Values (Out-of-Band)

```bash
# Create secret versions (replace <VALUE> with actual secrets)
echo -n "<your-jwt-secret-32-chars-minimum>" | \
  gcloud secrets versions add garda-jwt-secret --data-file=-

echo -n "<your-ingest-token>" | \
  gcloud secrets versions add garda-ingest-token --data-file=-

echo -n "<your-scoring-token>" | \
  gcloud secrets versions add garda-scoring-token --data-file=-

echo -n "<postgres-password>" | \
  gcloud secrets versions add garda-db-password --data-file=-
```

#### Phase 2.4c: Build and Push Images to Artifact Registry

Configure Docker for Artifact Registry and build images in each service repo:

```bash
# Configure Docker auth
gcloud auth configure-docker us-central1-docker.pkg.dev

# For each service repo (backend, frontend, scoring, ingest):
cd ../garda-ai-backend

# Build and tag image
docker build -t us-central1-docker.pkg.dev/garda-ai-platform/garda/backend:latest .

# Push image
docker push us-central1-docker.pkg.dev/garda-ai-platform/garda/backend:latest

# Repeat for frontend, scoring, ingest
# (Or trigger CI workflows to auto-push on push to main)
```

#### Phase 2.4d: Apply Full Infrastructure (Services + Jobs)

```bash
cd garda-ai-deploy/terraform

# Now apply the full Terraform plan (services, jobs, domain mappings)
terraform apply tfplan
```

---

## Phase 3: Deploy-Init Jobs

Before services take traffic, run the initialization jobs:

```bash
# 1. Run database migrations
gcloud run jobs execute garda-migrate \
  --region=us-central1 \
  --wait

# 2. Load reference dataset (ingest seed)
gcloud run jobs execute garda-ingest \
  --region=us-central1 \
  --wait
```

---

## Phase 4: Set Up Workload Identity Federation (CI/CD Authentication)

Each service repo needs GitHub Actions to authenticate to GCP with short-lived credentials (no long-lived API keys).

### Step 4.1: Create Workload Identity Provider

```bash
# Create the provider
gcloud iam workload-identity-pools create "github-pool" \
  --project=garda-ai-platform \
  --location=global \
  --display-name="GitHub Actions"

# Create OIDC provider configuration
gcloud iam workload-identity-providers create-oidc "github-provider" \
  --project=garda-ai-platform \
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
  --project=garda-ai-platform \
  --display-name="GitHub Actions Deployer"

# Grant Cloud Run deployment permissions
gcloud projects add-iam-policy-binding garda-ai-platform \
  --member=serviceAccount:github-deployer@garda-ai-platform.iam.gserviceaccount.com \
  --role=roles/run.admin

# Grant Artifact Registry push permissions
gcloud projects add-iam-policy-binding garda-ai-platform \
  --member=serviceAccount:github-deployer@garda-ai-platform.iam.gserviceaccount.com \
  --role=roles/artifactregistry.writer

# Allow GitHub to impersonate the service account
gcloud iam service-accounts add-iam-policy-binding \
  github-deployer@garda-ai-platform.iam.gserviceaccount.com \
  --project=garda-ai-platform \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/garda-ai-platform/locations/global/workloadIdentityPools/github-pool/attribute.repository/your-org/repo-name"
```

### Step 4.3: Set Repository Secrets and Variables

For each service repo (`garda-ai-backend`, `garda-ai-dashboard-web`, `garda-ai-scoring`, `garda-ai-ingest`):

**Repository Variables** (Settings → Secrets and variables → Variables):
- `GCP_PROJECT`: `garda-ai-platform`
- `GCP_REGION`: `us-central1`

**Repository Secrets** (Settings → Secrets and variables → Secrets):
- `GCP_WIF_PROVIDER`: The Workload Identity Provider resource name (from step 4.1 output)
- `GCP_DEPLOYER_SA`: `github-deployer@garda-ai-platform.iam.gserviceaccount.com`

Example WIF Provider name: `projects/123456/locations/global/workloadIdentityPools/github-pool/providers/github-provider`

---

## Phase 5: Domain & DNS

### Step 5.1: Create Cloud Run Domain Mappings

```bash
# Map frontend
gcloud run domain-mappings create \
  --service=garda-frontend \
  --domain=app.garda.example.com \
  --region=us-central1

# Map backend
gcloud run domain-mappings create \
  --service=garda-backend \
  --domain=api.garda.example.com \
  --region=us-central1
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
gcloud run services list --region=us-central1

gcloud run services describe garda-backend --region=us-central1
gcloud run services describe garda-frontend --region=us-central1
gcloud run services describe garda-scoring --region=us-central1
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
# Backend logs
gcloud run services logs read garda-backend --region=us-central1 --limit=50

# Scoring service logs
gcloud run services logs read garda-scoring --region=us-central1 --limit=50

# Ingest job execution logs
gcloud run jobs describe garda-ingest --region=us-central1
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

**Problem:** `gcloud run deploy` fails with "image not found in Artifact Registry"

**Solution:** Ensure images are pushed before running `terraform apply` (Phase 2.4c).

### Database Connection Timeouts

**Problem:** Backend fails to connect to Cloud SQL

**Solution:**
1. Verify VPC connector is attached to Cloud Run services
2. Check Cloud SQL private IP is in the same VPC
3. Verify Cloud SQL has the correct database and user

### Secret Access Denied

**Problem:** Services fail to access Secret Manager

**Solution:**
1. Verify service account has `roles/secretmanager.secretAccessor`
2. Check secret version exists (Step 4.2)
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
# List Cloud Run service revisions
gcloud run revisions list --service=garda-backend --region=us-central1

# Direct traffic to a previous revision
gcloud run services update-traffic garda-backend \
  --to-revisions=<PREVIOUS_REVISION_ID>=100 \
  --region=us-central1
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
