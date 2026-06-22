terraform {
  required_version = ">= 1.6"
}

# Skeleton only — fill in a provider (AWS/GCP/Azure) to provision:
#   - a managed PostgreSQL instance (the canonical store)
#   - a managed Redis
#   - container hosting for backend / pipeline / frontend images
# Intentionally empty so `terraform validate` passes without cloud credentials.
