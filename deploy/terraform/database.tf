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
