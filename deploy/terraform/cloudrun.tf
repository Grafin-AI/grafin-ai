locals {
  db_url    = "postgresql+asyncpg://grafin:${var.db_password}@${google_sql_database_instance.pg.private_ip_address}:5432/grafin"
  redis_url = "redis://${google_redis_instance.redis.host}:${google_redis_instance.redis.port}/0"
}

resource "google_cloud_run_v2_service" "scoring" {
  name     = "grafin-scoring"
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
        name = "GRAFIN_SCORING_TOKEN"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.s["grafin-scoring-token"].secret_id
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
  name     = "grafin-backend"
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
        name = "GRAFIN_DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.s["grafin-database-url"].secret_id
            version = "latest"
          }
        }
      }
      env {
        name  = "GRAFIN_REDIS_URL"
        value = local.redis_url
      }
      env {
        name  = "GRAFIN_SCORING_URL"
        value = google_cloud_run_v2_service.scoring.uri
      }
      env {
        name = "GRAFIN_JWT_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.s["grafin-jwt-secret"].secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "GRAFIN_INGEST_TOKEN"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.s["grafin-ingest-token"].secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "GRAFIN_SCORING_TOKEN"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.s["grafin-scoring-token"].secret_id
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
  name     = "grafin-frontend"
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
