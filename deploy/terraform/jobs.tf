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
          name = "GARDA_DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.s["garda-database-url"].secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }

  # NOTE: deliberately no lifecycle block here — the migrate job stays
  # terraform-owned so it tracks var.backend_image.
  # Ensure the jobs SA can read the DB-URL secret before the job mounts it.
  depends_on = [google_secret_manager_secret_iam_member.access]
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
          name = "GARDA_DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.s["garda-database-url"].secret_id
              version = "latest"
            }
          }
        }
        # The reference CSV is baked into the ingest image (simplest for the demo).
        # GARDA_DATA_DIR defaults to the image's bundled data path.
      }
    }
  }

  # terraform provisions this job; image rollout is owned by the operator
  # (`make deploy` in garda-ai-ingest -> gcloud run jobs deploy).
  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image]
  }

  # Ensure the jobs SA can read the DB-URL secret before the job mounts it.
  depends_on = [google_secret_manager_secret_iam_member.access]
}
