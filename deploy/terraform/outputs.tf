output "backend_url" {
  value = google_cloud_run_v2_service.backend.uri
}

output "frontend_url" {
  value = google_cloud_run_v2_service.frontend.uri
}

output "scoring_url" {
  value = google_cloud_run_v2_service.scoring.uri
}

output "artifact_repo" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.docker.repository_id}"
}

output "db_connection" {
  value = google_sql_database_instance.pg.connection_name
}

output "domain_dns_app" {
  value = try(google_cloud_run_domain_mapping.app[0].status[0].resource_records, [])
}

output "domain_dns_api" {
  value = try(google_cloud_run_domain_mapping.api[0].status[0].resource_records, [])
}
