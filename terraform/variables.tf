variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "asia-southeast1"
}

variable "domain" {
  type    = string
  default = "" # e.g. garda.example.com; "" disables domain mappings
}

variable "deploy_observability" {
  type    = bool
  default = false
}

# Image references (pushed by per-repo CI to Artifact Registry). Default to :latest.
variable "backend_image" {
  type = string
}

variable "scoring_image" {
  type = string
}

variable "frontend_image" {
  type = string
}

variable "ingest_image" {
  type = string
}

variable "db_tier" {
  type    = string
  default = "db-custom-1-3840"
}

variable "redis_tier" {
  type    = string
  default = "BASIC"
}

variable "redis_size_gb" {
  type    = number
  default = 1
}

# Secrets (provided out-of-band; never commit real values). Marked sensitive.
variable "jwt_secret" {
  type      = string
  sensitive = true
}

variable "ingest_token" {
  type      = string
  sensitive = true
}

variable "scoring_token" {
  type      = string
  sensitive = true
}

variable "db_password" {
  type      = string
  sensitive = true
}
