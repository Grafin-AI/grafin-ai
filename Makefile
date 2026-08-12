# Manual, operator-run deploy of the garda-ingest Cloud Run JOB.
#
# Prerequisites (once per machine):
#   gcloud auth login && gcloud config set project <your-project>
#   docker running
#
# Config: cp deploy.env.example deploy.env && edit it,
#         OR export GCP_PROJECT / GCP_REGION in your shell.
# Then:   make deploy    (build + push + deploy the job definition)
#         make execute   (run the job now to seed reference data)
-include deploy.env

JOB        := garda-ingest
IMAGE_NAME := ingest
TAG        ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo latest)

REGISTRY := $(GCP_REGION)-docker.pkg.dev/$(GCP_PROJECT)/garda
IMAGE    := $(REGISTRY)/$(IMAGE_NAME)

.PHONY: help check-env print-config build push deploy execute

help:
	@echo "make deploy        build, push, and update the $(JOB) job definition"
	@echo "make execute       run the $(JOB) job now (seeds reference data) and wait"
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
	@echo "JOB     = $(JOB)"

build: check-env
	docker build -t "$(IMAGE):$(TAG)" -t "$(IMAGE):latest" .

push: build
	gcloud auth configure-docker $(GCP_REGION)-docker.pkg.dev --quiet
	docker push "$(IMAGE):$(TAG)"
	docker push "$(IMAGE):latest"

deploy: push
	gcloud run jobs deploy $(JOB) --image "$(IMAGE):$(TAG)" --region $(GCP_REGION) --quiet
	@echo "Deployed job $(JOB) -> $(IMAGE):$(TAG)"

execute: check-env
	gcloud run jobs execute $(JOB) --region $(GCP_REGION) --wait
