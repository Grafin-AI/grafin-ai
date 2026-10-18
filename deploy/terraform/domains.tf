resource "google_cloud_run_domain_mapping" "app" {
  count    = var.domain == "" ? 0 : 1
  name     = "app.${var.domain}"
  location = var.region
  metadata {
    namespace = var.project_id
  }
  spec {
    route_name = google_cloud_run_v2_service.frontend.name
  }
}

resource "google_cloud_run_domain_mapping" "api" {
  count    = var.domain == "" ? 0 : 1
  name     = "api.${var.domain}"
  location = var.region
  metadata {
    namespace = var.project_id
  }
  spec {
    route_name = google_cloud_run_v2_service.backend.name
  }
}
