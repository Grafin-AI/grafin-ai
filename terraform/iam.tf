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
# produced by the setproduct() below (a resource block cannot be indexed by a
# dynamic string directly, so we route through this locals map).
locals {
  service_account_emails = {
    backend  = google_service_account.backend.email
    scoring  = google_service_account.scoring.email
    frontend = google_service_account.frontend.email
    jobs     = google_service_account.jobs.email
  }
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

# Secret accessor for the SAs that consume secrets (backend, scoring, jobs)
resource "google_secret_manager_secret_iam_member" "access" {
  for_each  = { for pair in setproduct(keys(local.secrets), ["backend", "scoring", "jobs"]) : "${pair[0]}-${pair[1]}" => pair }
  secret_id = google_secret_manager_secret.s[each.value[0]].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${local.service_account_emails[each.value[1]]}"
}

# Backend may invoke the internal scoring service (service-to-service auth)
resource "google_cloud_run_v2_service_iam_member" "backend_invokes_scoring" {
  name     = google_cloud_run_v2_service.scoring.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.backend.email}"
}
