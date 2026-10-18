# Manual, Operator-Run Deploy — Design

**Date:** 2026-08-11
**Status:** Approved (design)
**Scope:** Change *how a deploy is triggered*. No architecture, service-topology, compose, or app-code changes.

---

## Problem

Today each deployable service repo carries a `deploy.yml` that runs **automatically on push to `main`** (build → push to Artifact Registry → `gcloud run deploy`). The team's workflow never pushes directly to `main` — changes land via PR from `dev` → `main` — and, more importantly, the team wants deploys to be a **deliberate, operator-run action**, not a side effect of a merge. An ops person should clone the repo, authenticate, and deploy by hand.

## Goal

For each of the four deployable repos (`grafin-ai-backend`, `grafin-ai-scoring`, `grafin-ai-dashboard-web`, `grafin-ai-ingest`):

1. Add a **local `make deploy`** an operator runs after cloning (build → push → deploy). It mirrors `deploy.yml` step-for-step so both routes produce identical results.
2. Flip **`deploy.yml` from auto (`push: main`) to a manual button (`workflow_dispatch`)** — it never fires on a merge; it only runs when someone clicks *Run workflow*.

Plus one supporting infra change and doc updates:

3. Add `lifecycle { ignore_changes = [...image] }` to the terraform Cloud Run **services** and the **ingest job**, so terraform (which *creates* the resource with its VPC/secret/ingress wiring) and `make deploy`/`gcloud` (which *rolls new images*) stop fighting over the image field.
4. Update the GCP runbook to describe both manual routes and the corrected deploy sequence.

**Non-goals / untouched:** `grafin-ai-sim` (never deployed — no Makefile-deploy, no workflow change); the platform architecture; `docker-compose.yml`; the observability stack; the WIF setup itself (still used by the `workflow_dispatch` route). No new repos.

---

## Division of labor (the mental model)

| Concern | Owner |
|---|---|
| **Provision** a Cloud Run service/job (VPC connector, secret refs, ingress, service account, scaling, timeout) | **terraform** — creates it once, keeps the wiring in sync |
| **Roll a new image** onto an already-provisioned service/job | **`make deploy`** (local) or the `workflow_dispatch` button — `gcloud run deploy --image <tag>` creates a new revision, preserving all other config |

This is why terraform needs `ignore_changes` on the image: without it, the next `terraform apply` would revert the service to `var.*_image` and undo the operator's rollout. With it, terraform provisions the resource with `var.*_image` **on create**, then leaves the image alone forever after; `make deploy` owns it from then on.

`gcloud run deploy <service> --image <tag>` against an **existing** service updates only the image (new revision, same VPC/secrets/ingress). Against a **non-existent** service it would create a bare one with none of that wiring — so `make deploy` is strictly for **already-provisioned** (terraform-created) services. Cold start seeds the first image with `make push` (build+push only), *then* terraform creates the services.

---

## Change 1 — per-repo `Makefile` with `make deploy`

Each of the four repos gets a root `Makefile`. Config comes from two env vars — **the same names the workflow uses** — supplied either by a gitignored `deploy.env` file (auto-included) or by shell `export`:

- `GCP_PROJECT` (required)
- `GCP_REGION` (required)
- `TAG` — optional; defaults to the git short SHA (falls back to `latest` outside a git checkout)

Derived: `IMAGE = $(GCP_REGION)-docker.pkg.dev/$(GCP_PROJECT)/grafin/<name>`.

**Config file mechanism.** A committed `deploy.env.example` holds `KEY=value` lines (valid as *both* a Makefile include and a shell-sourceable file). The operator copies it to `deploy.env` (gitignored) and edits, or ignores the file and `export`s the vars. The Makefile begins with `-include deploy.env` (the leading `-` makes a missing file a no-op). Recipes reference `$(GCP_PROJECT)`/`$(GCP_REGION)` directly, so no `export` gymnastics are needed; shell-exported env vars are auto-imported by make as a fallback.

**Target chain (services — backend/scoring/frontend):**

```makefile
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

SERVICE    := grafin-backend        # grafin-scoring / grafin-frontend
IMAGE_NAME := backend              # scoring / frontend
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
```

**ingest differs (it's a Cloud Run *job*, not a service):** it uses `JOB := grafin-ingest`, its `deploy` target runs `gcloud run jobs deploy grafin-ingest --image ... --region ...`, and it adds an `execute` convenience target (`gcloud run jobs execute grafin-ingest --region $(GCP_REGION) --wait`) since deploying a job does not run it.

**Image / service / job names** (must match the existing `deploy.yml` and terraform exactly):

| Repo | `IMAGE_NAME` | Target name | Deploy verb |
|---|---|---|---|
| grafin-ai-backend | `backend` | service `grafin-backend` | `gcloud run deploy` |
| grafin-ai-scoring | `scoring` | service `grafin-scoring` | `gcloud run deploy` |
| grafin-ai-dashboard-web | `frontend` | service `grafin-frontend` | `gcloud run deploy` |
| grafin-ai-ingest | `ingest` | job `grafin-ingest` | `gcloud run jobs deploy` (+ `make execute`) |

**gitignore.** Add `deploy.env` to each repo's `.gitignore` (none currently ignore that exact name; the `.env.*` patterns in backend/dashboard do **not** match `deploy.env`, and their `!.env.example` negation would wrongly hide a `.env.deploy.example` — which is the reason for choosing the `deploy.env` name). `deploy.env.example` stays committed.

---

## Change 2 — `deploy.yml`: `push: main` → `workflow_dispatch`

In all four `deploy.yml`, replace:

```yaml
on:
  push:
    branches: [main]
```

with:

```yaml
on:
  workflow_dispatch:
```

Everything else (WIF auth via `google-github-actions/auth@v2`, `permissions: {contents: read, id-token: write}`, build/push, `gcloud run deploy` / `gcloud run jobs deploy`) is unchanged. `github.sha` remains valid under `workflow_dispatch` (it resolves to the SHA of the ref selected in the *Run workflow* dropdown). CI (`ci.yml`, lint/test on PRs) is untouched.

---

## Change 3 — terraform `ignore_changes` on the image

In `grafin-ai-deploy/terraform/cloudrun.tf`, add a `lifecycle` block to each of the three services:

```hcl
lifecycle {
  ignore_changes = [template[0].containers[0].image]
}
```

In `grafin-ai-deploy/terraform/jobs.tf`, add to the **ingest** job (nested template path):

```hcl
lifecycle {
  ignore_changes = [template[0].template[0].containers[0].image]
}
```

The **migrate** job is left terraform-owned (no `lifecycle`): nobody runs `make deploy` against it, and it should track `var.backend_image`. Documented caveat: to run a *new* migration after a backend deploy, `terraform apply` (which re-resolves the backend `:latest` digest onto the migrate job) then `gcloud run jobs execute grafin-migrate --wait`.

`terraform fmt` and `tofu validate` must stay green.

---

## Change 4 — docs

Update `grafin-ai-deploy/docs/deploy/gcp-runbook.md`:

- Replace the "push each service repo to `main` → `deploy.yml` triggers" language with the two manual routes: local `make deploy`, or the GitHub *Run workflow* (`workflow_dispatch`) button.
- Add a **Deploy sequence** section capturing both modes:
  - **Cold start (once):** foundation `terraform apply` → `make push` per service (seed first image) → full `terraform apply` (creates services/jobs) → `gcloud run jobs execute grafin-migrate --wait` → `make execute` in ingest (seed reference data).
  - **Routine redeploy (common):** in the service repo, `make deploy` (build → push → `gcloud run deploy`). No terraform, no other services touched.
- Note WIF is required only for the `workflow_dispatch` route; local `make deploy` uses the operator's own `gcloud auth login`.

Grep the `docs/` tree for any remaining stale "auto-deploy on push to main" / "on: push" deploy references and correct them.

---

## Testing & verification

These are shell/YAML/HCL config, not app code — so no unit tests. Verification per repo:

- `make -n deploy` prints the correct command sequence (build → push → deploy) with `GCP_PROJECT`/`GCP_REGION` set.
- `make deploy` (or `make check-env`) **fails fast with a clear message** when `GCP_PROJECT` is unset. (No real build/push is exercised in CI-less verification — the point is the guard fires.)
- Each `deploy.yml` parses as valid workflow YAML and its only trigger is `workflow_dispatch`.
- `terraform fmt -check` and `tofu validate` pass in `grafin-ai-deploy/terraform/`.
- Grep confirms no `deploy.env` is committed and no stale `on: push` auto-deploy language remains in docs.

---

## Commits

All commits authored **Thariq Iskandar Zulkarnain M P `<thariqiskandar9@gmail.com>`** with trailer **`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`**. Committed locally to each repo (consistent with the prior phases; no remote push unless the user asks).
