locals {
  secrets = {
    "garda-jwt-secret"    = var.jwt_secret
    "garda-ingest-token"  = var.ingest_token
    "garda-scoring-token" = var.scoring_token
    "garda-db-password"   = var.db_password
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
