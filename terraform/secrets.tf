locals {
  # NOTE: the DB DSN (garda-database-url) is stored as a secret and injected via
  # secret_key_ref so the password never rides in a plaintext env var. var.db_password
  # is still used directly to create the google_sql_user (see database.tf).
  secrets = {
    "garda-jwt-secret"    = var.jwt_secret
    "garda-ingest-token"  = var.ingest_token
    "garda-scoring-token" = var.scoring_token
    "garda-database-url"  = local.db_url
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
