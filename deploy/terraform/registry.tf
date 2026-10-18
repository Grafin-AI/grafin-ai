resource "google_artifact_registry_repository" "docker" {
  location      = var.region
  repository_id = "grafin"
  format        = "DOCKER"
  depends_on    = [google_project_service.enabled]
}
