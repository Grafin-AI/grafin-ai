# Switchable observability stack.
#
# When `deploy_observability = false` (default) NOTHING here is provisioned and
# the platform relies on Cloud Monitoring / Google Managed Prometheus.
#
# When `deploy_observability = true` we provision a minimal self-hosted stack: a
# single small GCE VM sitting inside the VPC (so it can scrape the backend /
# scoring `/metrics` endpoints over private ranges). It is intentionally lean —
# Prometheus + Grafana are expected to be started via the VM startup script /
# baked image. Everything is gated behind `count` so the boundary is a clean
# on/off switch that `terraform validate` is happy with in both states.
locals {
  observability_enabled = var.deploy_observability
}

resource "google_service_account" "observability" {
  count       = local.observability_enabled ? 1 : 0
  account_id  = "grafin-observability"
  description = "Runs the self-hosted Prometheus + Grafana VM"
}

resource "google_compute_instance" "observability" {
  count        = local.observability_enabled ? 1 : 0
  name         = "grafin-observability"
  machine_type = "e2-small"
  zone         = "${var.region}-a"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
    }
  }

  # Reachable inside the VPC to scrape the backend/scoring /metrics endpoints.
  # The ephemeral external IP (access_config) lets the startup script pull the
  # Docker/apt packages it needs to bootstrap Prometheus + Grafana.
  network_interface {
    network    = google_compute_network.vpc.id
    subnetwork = google_compute_subnetwork.subnet.id
    access_config {}
  }

  service_account {
    email = google_service_account.observability[0].email
    # Narrow scopes: just enough to write logs/metrics, not full cloud-platform.
    scopes = [
      "https://www.googleapis.com/auth/logging.write",
      "https://www.googleapis.com/auth/monitoring.write",
    ]
  }

  # Minimal bootstrap: install Prometheus + Grafana via Docker. Real scrape
  # configs are managed out-of-band. The Grafana admin password is injected from
  # var.grafana_admin_password rather than defaulting to admin/admin.
  metadata_startup_script = <<-EOT
    #!/bin/bash
    set -euo pipefail
    apt-get update && apt-get install -y docker.io
    systemctl enable --now docker
    docker run -d --name prometheus -p 9090:9090 prom/prometheus
    docker run -d --name grafana -p 3000:3000 \
      -e GF_SECURITY_ADMIN_PASSWORD='${var.grafana_admin_password}' \
      grafana/grafana
  EOT

  depends_on = [google_project_service.enabled]
}
