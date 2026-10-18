resource "google_service_account" "backend" {
  account_id = "garda-backend"
}
resource "google_service_account" "scoring" {
  account_id = "garda-scoring"
}
resource "google_service_account" "frontend" {
  account_id = "garda-frontend"
}
resource "google_service_account" "jobs" {
  account_id = "garda-jobs"
}

# Map of workload -> service account email, so we can index by the string keys
# in the least-privilege secret_access map below (a resource block cannot be
# indexed by a dynamic string directly, so we route through this locals map).
locals {
  service_account_emails = {
    backend  = google_service_account.backend.email
    scoring  = google_service_account.scoring.email
    frontend = google_service_account.frontend.email
    jobs     = google_service_account.jobs.email
  }

  # Least-privilege: each secret is readable ONLY by the workloads that need it.
  # (The internal scoring SA must NOT be able to read the JWT secret or the DB URL.)
  secret_access = {
    "garda-jwt-secret"    = ["backend"]
    "garda-ingest-token"  = ["backend"]
    "garda-scoring-token" = ["backend", "scoring"]
    "garda-database-url"  = ["backend", "jobs"]
  }

  # Flatten to { "<secret>-<workload>" => { secret, workload } } for for_each.
  secret_access_flat = merge([
    for secret, workloads in local.secret_access : {
      for wl in workloads : "${secret}-${wl}" => { secret = secret, workload = wl }
    }
  ]...)
}

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

# Secret accessor, scoped per-secret to only the workloads that need each one.
resource "google_secret_manager_secret_iam_member" "access" {
  for_each  = local.secret_access_flat
  secret_id = google_secret_manager_secret.s[each.value.secret].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${local.service_account_emails[each.value.workload]}"
}

# Scoring stays ingress = INGRESS_TRAFFIC_INTERNAL_ONLY (the network gate), so
# it is never publicly reachable. Granting allUsers the invoker role does NOT
# expose it — it only removes the Google OIDC ID-token requirement so that the
# app's GARDA_SCORING_TOKEN header is the real service-to-service auth.
resource "google_cloud_run_v2_service_iam_member" "scoring_invoker" {
  name     = google_cloud_run_v2_service.scoring.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}
