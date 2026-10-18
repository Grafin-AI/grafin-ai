locals {
  # NOTE: the DB DSN (grafin-database-url) is stored as a secret and injected via
  # secret_key_ref so the password never rides in a plaintext env var. var.db_password
  # is still used directly to create the google_sql_user (see database.tf).
  secrets = {
    "grafin-jwt-secret"    = var.jwt_secret
    "grafin-ingest-token"  = var.ingest_token
    "grafin-scoring-token" = var.scoring_token
    "grafin-database-url"  = local.db_url
  }
}

resource "google_secret_manager_secret" "s" {
  for_each  = local.secrets
  secret_id = each.key
  replication {
    auto {}
  }
  depends_on = [google_project_service.enabled]
}

resource "google_secret_manager_secret_version" "v" {
  for_each    = local.secrets
  secret      = google_secret_manager_secret.s[each.key].id
  secret_data = each.value
}
