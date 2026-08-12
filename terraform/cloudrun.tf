locals {
  db_url    = "postgresql+asyncpg://garda:${var.db_password}@${google_sql_database_instance.pg.private_ip_address}:5432/garda"
  redis_url = "redis://${google_redis_instance.redis.host}:${google_redis_instance.redis.port}/0"
}

resource "google_cloud_run_v2_service" "scoring" {
  name     = "garda-scoring"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  template {
    service_account = google_service_account.scoring.email
    vpc_access {
      connector = google_vpc_access_connector.connector.id
      egress    = "PRIVATE_RANGES_ONLY"
    }
    containers {
      image = var.scoring_image
      ports {
        container_port = 8000
      }
      env {
        name = "GARDA_SCORING_TOKEN"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.s["garda-scoring-token"].secret_id
            version = "latest"
          }
        }
      }
    }
  }

  # terraform provisions this service; image rollout is owned by the operator
  # (`make deploy` / the workflow_dispatch button -> gcloud run deploy).
  lifecycle {
    ignore_changes = [template[0].containers[0].image]
  }

  # Ensure the scoring SA can read its secret before the service mounts it.
  depends_on = [google_secret_manager_secret_iam_member.access]
}

resource "google_cloud_run_v2_service" "backend" {
  name     = "garda-backend"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.backend.email
    scaling {
      min_instance_count = 1 # keep the WS relay + Redis subscription warm
    }
    vpc_access {
      connector = google_vpc_access_connector.connector.id
      # ALL_TRAFFIC so the call to scoring's *.run.app URL is routed through the
      # connector and seen as internal (matching scoring's INTERNAL_ONLY ingress).
      # Backend has no other outbound needs, so no Cloud NAT is required.
      egress = "ALL_TRAFFIC"
    }
    containers {
      image = var.backend_image
      ports {
        container_port = 8000
      }
      env {
        name = "GARDA_DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.s["garda-database-url"].secret_id
            version = "latest"
          }
        }
      }
      env {
        name  = "GARDA_REDIS_URL"
        value = local.redis_url
      }
      env {
        name  = "GARDA_SCORING_URL"
        value = google_cloud_run_v2_service.scoring.uri
      }
      env {
        name = "GARDA_JWT_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.s["garda-jwt-secret"].secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "GARDA_INGEST_TOKEN"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.s["garda-ingest-token"].secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "GARDA_SCORING_TOKEN"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.s["garda-scoring-token"].secret_id
            version = "latest"
          }
        }
      }
    }
    # WebSocket relay: allow long-lived requests
    timeout = "3600s"
  }

  # terraform provisions this service; image rollout is owned by the operator
  # (`make deploy` / the workflow_dispatch button -> gcloud run deploy).
  lifecycle {
    ignore_changes = [template[0].containers[0].image]
  }

  # Ensure the backend SA can read its secrets before the service mounts them.
  depends_on = [google_secret_manager_secret_iam_member.access]
}

# Backend is public: allow unauthenticated (app enforces JWT/ingest-token itself)
resource "google_cloud_run_v2_service_iam_member" "backend_public" {
  name     = google_cloud_run_v2_service.backend.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service" "frontend" {
  name     = "garda-frontend"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.frontend.email
    containers {
      image = var.frontend_image
      ports {
        container_port = 8080
      }
      env {
        name  = "BACKEND_URL" # consumed by the templated nginx.conf (plan 3)
        value = google_cloud_run_v2_service.backend.uri
      }
    }
  }

  # terraform provisions this service; image rollout is owned by the operator
  # (`make deploy` / the workflow_dispatch button -> gcloud run deploy).
  lifecycle {
    ignore_changes = [template[0].containers[0].image]
  }
}

resource "google_cloud_run_v2_service_iam_member" "frontend_public" {
  name     = google_cloud_run_v2_service.frontend.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}
