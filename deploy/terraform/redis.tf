resource "google_redis_instance" "redis" {
  name               = "garda-redis"
  tier               = var.redis_tier
  memory_size_gb     = var.redis_size_gb
  region             = var.region
  authorized_network = google_compute_network.vpc.id
  connect_mode       = "PRIVATE_SERVICE_ACCESS"
  depends_on         = [google_service_networking_connection.psa]
}
