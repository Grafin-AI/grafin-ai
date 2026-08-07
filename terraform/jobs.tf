resource "google_cloud_run_v2_job" "migrate" {
  name     = "garda-migrate"
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
          name  = "GARDA_DATABASE_URL"
          value = local.db_url
        }
      }
    }
  }
}

resource "google_cloud_run_v2_job" "ingest" {
  name     = "garda-ingest"
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
          name  = "GARDA_DATABASE_URL"
          value = local.db_url
        }
        # The reference CSV is baked into the ingest image (simplest for the demo).
        # GARDA_DATA_DIR defaults to the image's bundled data path.
      }
    }
  }
}
