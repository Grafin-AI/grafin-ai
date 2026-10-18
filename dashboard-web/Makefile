# Manual, operator-run deploy to GCP Cloud Run.
#
# Prerequisites (once per machine):
#   gcloud auth login && gcloud config set project <your-project>
#   docker running
#
# Config: cp deploy.env.example deploy.env && edit it,
#         OR export GCP_PROJECT / GCP_REGION in your shell.
# Then:   make deploy
-include deploy.env

SERVICE    := grafin-frontend
IMAGE_NAME := frontend
TAG        ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo latest)

REGISTRY := $(GCP_REGION)-docker.pkg.dev/$(GCP_PROJECT)/grafin
IMAGE    := $(REGISTRY)/$(IMAGE_NAME)

.PHONY: help check-env print-config build push deploy

help:
	@echo "make deploy        build, push, and roll a new revision of $(SERVICE)"
	@echo "make push          build + push image tags (use for first-time image seeding)"
	@echo "make build         docker build only"
	@echo "make print-config  show resolved PROJECT / REGION / IMAGE / TAG"

check-env:
	@test -n "$(GCP_PROJECT)" || { echo "ERROR: GCP_PROJECT is not set (edit deploy.env or 'export GCP_PROJECT=...')"; exit 1; }
	@test -n "$(GCP_REGION)"  || { echo "ERROR: GCP_REGION is not set (edit deploy.env or 'export GCP_REGION=...')";  exit 1; }
	@command -v gcloud >/dev/null 2>&1 || { echo "ERROR: gcloud CLI not found (install the Google Cloud SDK)"; exit 1; }
	@command -v docker >/dev/null 2>&1 || { echo "ERROR: docker not found (is Docker running?)"; exit 1; }

print-config: check-env
	@echo "PROJECT = $(GCP_PROJECT)"
	@echo "REGION  = $(GCP_REGION)"
	@echo "IMAGE   = $(IMAGE):$(TAG)"
	@echo "SERVICE = $(SERVICE)"

build: check-env
	docker build -t "$(IMAGE):$(TAG)" -t "$(IMAGE):latest" .

push: build
	gcloud auth configure-docker $(GCP_REGION)-docker.pkg.dev --quiet
	docker push "$(IMAGE):$(TAG)"
	docker push "$(IMAGE):latest"

deploy: push
	gcloud run deploy $(SERVICE) --image "$(IMAGE):$(TAG)" --region $(GCP_REGION) --quiet
	@echo "Deployed $(SERVICE) -> $(IMAGE):$(TAG)"
