# Manual, Operator-Run Deploy — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace push-to-main auto-deploy with a deliberate operator action: a local `make deploy` in each deployable repo plus a manual `workflow_dispatch` GitHub button, and stop terraform from reverting operator image rollouts.

**Architecture:** terraform *creates* each Cloud Run service/job (VPC connector, secret refs, ingress, SA); `make deploy` / the `workflow_dispatch` button *roll new images* onto the already-provisioned resource via `gcloud run deploy --image`. `lifecycle { ignore_changes = [...image] }` keeps the two from fighting over the image field. Cold start seeds the first image with `make push` then `terraform apply` creates the services; `make deploy` is for routine redeploys.

**Tech Stack:** GNU Make, GitHub Actions YAML, Terraform/OpenTofu HCL, gcloud. No app-code changes.

**Spec:** `garda-ai-deploy/docs/superpowers/specs/2026-08-11-manual-deploy-design.md`

**Repo root for all paths:** `/Users/thariqiskandar/Documents/Career/BI - OJK Hackathon 2025/repositories/`

**Commit identity (every commit):** author `Thariq Iskandar Zulkarnain M P <thariqiskandar9@gmail.com>`, trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Commit locally to `main` in each repo; do **not** push to any remote. Before the first commit in a repo, verify `git config user.email` is `thariqiskandar9@gmail.com` and set it locally if not.

---

## Task 1: `garda-ai-backend` — Makefile + workflow_dispatch

**Files:**
- Create: `garda-ai-backend/Makefile`
- Create: `garda-ai-backend/deploy.env.example`
- Modify: `garda-ai-backend/.gitignore` (add `deploy.env`)
- Modify: `garda-ai-backend/.github/workflows/deploy.yml` (trigger only)

- [ ] **Step 1: Create `garda-ai-backend/Makefile`**

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

SERVICE    := garda-backend
IMAGE_NAME := backend
TAG        ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo latest)

REGISTRY := $(GCP_REGION)-docker.pkg.dev/$(GCP_PROJECT)/garda
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

**Note on Makefile indentation:** recipe lines MUST be indented with a TAB, not spaces, or `make` errors with "missing separator".

- [ ] **Step 2: Create `garda-ai-backend/deploy.env.example`**

```bash
# Copy this file to deploy.env (gitignored) and edit, OR export these in your shell.
# These names match the GitHub Actions repo variables used by deploy.yml.
GCP_PROJECT=your-gcp-project
GCP_REGION=asia-southeast1
```

- [ ] **Step 3: Add `deploy.env` to `.gitignore`**

Append this line to `garda-ai-backend/.gitignore` (the existing `.env.*` pattern does NOT match `deploy.env`):

```
deploy.env
```

- [ ] **Step 4: Flip the workflow trigger in `garda-ai-backend/.github/workflows/deploy.yml`**

Replace:

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

Leave the rest of the file (env, permissions, jobs, WIF auth, build/push, `gcloud run deploy`) exactly as-is.

- [ ] **Step 5: Verify the guard fires when config is missing**

Run: `cd garda-ai-backend && env -u GCP_PROJECT -u GCP_REGION make check-env; echo "exit=$?"`
Expected: prints `ERROR: GCP_PROJECT is not set ...` and `exit=1`.

- [ ] **Step 6: Verify the deploy command sequence (dry run, executes nothing)**

Run: `cd garda-ai-backend && GCP_PROJECT=demo-proj GCP_REGION=asia-southeast1 make -n deploy`
Expected output includes, in order:
- `docker build -t "asia-southeast1-docker.pkg.dev/demo-proj/garda/backend:<sha>" -t "asia-southeast1-docker.pkg.dev/demo-proj/garda/backend:latest" .`
- `docker push` of both tags
- `gcloud run deploy garda-backend --image "asia-southeast1-docker.pkg.dev/demo-proj/garda/backend:<sha>" --region asia-southeast1 --quiet`

- [ ] **Step 7: Verify the workflow parses and triggers only on workflow_dispatch**

Run:
```bash
cd garda-ai-backend
python3 -c "import yaml; d=yaml.safe_load(open('.github/workflows/deploy.yml')); print(d.get(True) or d.get('on'))"
grep -nE "on:|workflow_dispatch|push:" .github/workflows/deploy.yml
```
Expected: the parsed trigger is `{'workflow_dispatch': None}` (note: PyYAML parses the YAML key `on` as boolean `True`, hence `d.get(True)`); grep shows `workflow_dispatch` and NO `push:`.

- [ ] **Step 8: Commit**

```bash
cd garda-ai-backend
git add Makefile deploy.env.example .gitignore .github/workflows/deploy.yml
git commit -m "feat: manual make deploy + workflow_dispatch (no auto-deploy on main)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: `garda-ai-scoring` — Makefile + workflow_dispatch

**Files:**
- Create: `garda-ai-scoring/Makefile`
- Create: `garda-ai-scoring/deploy.env.example`
- Modify: `garda-ai-scoring/.gitignore` (add `deploy.env`)
- Modify: `garda-ai-scoring/.github/workflows/deploy.yml` (trigger only)

- [ ] **Step 1: Create `garda-ai-scoring/Makefile`** (identical to Task 1 except `SERVICE`/`IMAGE_NAME`)

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

SERVICE    := garda-scoring
IMAGE_NAME := scoring
TAG        ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo latest)

REGISTRY := $(GCP_REGION)-docker.pkg.dev/$(GCP_PROJECT)/garda
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

(Recipe lines MUST use TAB indentation.)

- [ ] **Step 2: Create `garda-ai-scoring/deploy.env.example`**

```bash
# Copy this file to deploy.env (gitignored) and edit, OR export these in your shell.
# These names match the GitHub Actions repo variables used by deploy.yml.
GCP_PROJECT=your-gcp-project
GCP_REGION=asia-southeast1
```

- [ ] **Step 3: Add `deploy.env` to `.gitignore`**

Append to `garda-ai-scoring/.gitignore` (currently only ignores `.venv`):

```
deploy.env
```

- [ ] **Step 4: Flip the workflow trigger in `garda-ai-scoring/.github/workflows/deploy.yml`**

Replace `on:\n  push:\n    branches: [main]` with `on:\n  workflow_dispatch:`. Leave everything else as-is.

- [ ] **Step 5: Verify the guard fires**

Run: `cd garda-ai-scoring && env -u GCP_PROJECT -u GCP_REGION make check-env; echo "exit=$?"`
Expected: `ERROR: GCP_PROJECT is not set ...` and `exit=1`.

- [ ] **Step 6: Verify the deploy command sequence**

Run: `cd garda-ai-scoring && GCP_PROJECT=demo-proj GCP_REGION=asia-southeast1 make -n deploy`
Expected: `docker build` of `.../garda/scoring:<sha>` + `:latest`, both `docker push`, then `gcloud run deploy garda-scoring --image ".../garda/scoring:<sha>" --region asia-southeast1 --quiet`.

- [ ] **Step 7: Verify the workflow parses and triggers only on workflow_dispatch**

Run:
```bash
cd garda-ai-scoring
python3 -c "import yaml; d=yaml.safe_load(open('.github/workflows/deploy.yml')); print(d.get(True) or d.get('on'))"
grep -nE "on:|workflow_dispatch|push:" .github/workflows/deploy.yml
```
Expected: trigger is `{'workflow_dispatch': None}`; NO `push:`.

- [ ] **Step 8: Commit**

```bash
cd garda-ai-scoring
git add Makefile deploy.env.example .gitignore .github/workflows/deploy.yml
git commit -m "feat: manual make deploy + workflow_dispatch (no auto-deploy on main)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: `garda-ai-dashboard-web` — Makefile + workflow_dispatch

**Files:**
- Create: `garda-ai-dashboard-web/Makefile`
- Create: `garda-ai-dashboard-web/deploy.env.example`
- Modify: `garda-ai-dashboard-web/.gitignore` (add `deploy.env`)
- Modify: `garda-ai-dashboard-web/.github/workflows/deploy.yml` (trigger only)

- [ ] **Step 1: Create `garda-ai-dashboard-web/Makefile`** (service = `garda-frontend`, image = `frontend`)

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

SERVICE    := garda-frontend
IMAGE_NAME := frontend
TAG        ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo latest)

REGISTRY := $(GCP_REGION)-docker.pkg.dev/$(GCP_PROJECT)/garda
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

(Recipe lines MUST use TAB indentation.)

- [ ] **Step 2: Create `garda-ai-dashboard-web/deploy.env.example`**

```bash
# Copy this file to deploy.env (gitignored) and edit, OR export these in your shell.
# These names match the GitHub Actions repo variables used by deploy.yml.
GCP_PROJECT=your-gcp-project
GCP_REGION=asia-southeast1
```

- [ ] **Step 3: Add `deploy.env` to `.gitignore`**

Append to `garda-ai-dashboard-web/.gitignore` (its `.env.*` pattern does NOT match `deploy.env`):

```
deploy.env
```

- [ ] **Step 4: Flip the workflow trigger in `garda-ai-dashboard-web/.github/workflows/deploy.yml`**

Replace `on:\n  push:\n    branches: [main]` with `on:\n  workflow_dispatch:`. Leave everything else as-is.

- [ ] **Step 5: Verify the guard fires**

Run: `cd garda-ai-dashboard-web && env -u GCP_PROJECT -u GCP_REGION make check-env; echo "exit=$?"`
Expected: `ERROR: GCP_PROJECT is not set ...` and `exit=1`.

- [ ] **Step 6: Verify the deploy command sequence**

Run: `cd garda-ai-dashboard-web && GCP_PROJECT=demo-proj GCP_REGION=asia-southeast1 make -n deploy`
Expected: `docker build` of `.../garda/frontend:<sha>` + `:latest`, both `docker push`, then `gcloud run deploy garda-frontend --image ".../garda/frontend:<sha>" --region asia-southeast1 --quiet`.

- [ ] **Step 7: Verify the workflow parses and triggers only on workflow_dispatch**

Run:
```bash
cd garda-ai-dashboard-web
python3 -c "import yaml; d=yaml.safe_load(open('.github/workflows/deploy.yml')); print(d.get(True) or d.get('on'))"
grep -nE "on:|workflow_dispatch|push:" .github/workflows/deploy.yml
```
Expected: trigger is `{'workflow_dispatch': None}`; NO `push:`.

- [ ] **Step 8: Commit**

```bash
cd garda-ai-dashboard-web
git add Makefile deploy.env.example .gitignore .github/workflows/deploy.yml
git commit -m "feat: manual make deploy + workflow_dispatch (no auto-deploy on main)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

**Note:** if `git config user.email` is not `thariqiskandar9@gmail.com` in this repo (it previously held a corp email), set it locally first: `git config user.email thariqiskandar9@gmail.com`.

---

## Task 4: `garda-ai-ingest` — Makefile (job variant) + workflow_dispatch

**Files:**
- Create: `garda-ai-ingest/Makefile`
- Create: `garda-ai-ingest/deploy.env.example`
- Modify: `garda-ai-ingest/.gitignore` (add `deploy.env`)
- Modify: `garda-ai-ingest/.github/workflows/deploy.yml` (trigger only)

- [ ] **Step 1: Create `garda-ai-ingest/Makefile`** (Cloud Run **job**, not service; adds `execute`)

```makefile
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
```

(Recipe lines MUST use TAB indentation.)

- [ ] **Step 2: Create `garda-ai-ingest/deploy.env.example`**

```bash
# Copy this file to deploy.env (gitignored) and edit, OR export these in your shell.
# These names match the GitHub Actions repo variables used by deploy.yml.
GCP_PROJECT=your-gcp-project
GCP_REGION=asia-southeast1
```

- [ ] **Step 3: Add `deploy.env` to `.gitignore`**

Append to `garda-ai-ingest/.gitignore` (it ignores `.env` exactly, which does NOT match `deploy.env`):

```
deploy.env
```

- [ ] **Step 4: Flip the workflow trigger in `garda-ai-ingest/.github/workflows/deploy.yml`**

Replace `on:\n  push:\n    branches: [main]` with `on:\n  workflow_dispatch:`. Leave the rest (including `gcloud run jobs deploy garda-ingest`) as-is.

- [ ] **Step 5: Verify the guard fires**

Run: `cd garda-ai-ingest && env -u GCP_PROJECT -u GCP_REGION make check-env; echo "exit=$?"`
Expected: `ERROR: GCP_PROJECT is not set ...` and `exit=1`.

- [ ] **Step 6: Verify the deploy + execute command sequences**

Run:
```bash
cd garda-ai-ingest
GCP_PROJECT=demo-proj GCP_REGION=asia-southeast1 make -n deploy
GCP_PROJECT=demo-proj GCP_REGION=asia-southeast1 make -n execute
```
Expected: `deploy` shows `docker build`/`docker push` of `.../garda/ingest:<sha>`+`:latest` then `gcloud run jobs deploy garda-ingest --image ".../garda/ingest:<sha>" --region asia-southeast1 --quiet`; `execute` shows `gcloud run jobs execute garda-ingest --region asia-southeast1 --wait`.

- [ ] **Step 7: Verify the workflow parses and triggers only on workflow_dispatch**

Run:
```bash
cd garda-ai-ingest
python3 -c "import yaml; d=yaml.safe_load(open('.github/workflows/deploy.yml')); print(d.get(True) or d.get('on'))"
grep -nE "on:|workflow_dispatch|push:" .github/workflows/deploy.yml
```
Expected: trigger is `{'workflow_dispatch': None}`; NO `push:`.

- [ ] **Step 8: Commit**

```bash
cd garda-ai-ingest
git add Makefile deploy.env.example .gitignore .github/workflows/deploy.yml
git commit -m "feat: manual make deploy/execute + workflow_dispatch (no auto-deploy on main)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: `garda-ai-deploy/terraform` — `ignore_changes` on the image

**Files:**
- Modify: `garda-ai-deploy/terraform/cloudrun.tf` (3 services)
- Modify: `garda-ai-deploy/terraform/jobs.tf` (ingest job only)

- [ ] **Step 1: Add `lifecycle` to the `scoring` service in `cloudrun.tf`**

Inside `resource "google_cloud_run_v2_service" "scoring"`, add a `lifecycle` block (place it just before the existing `depends_on` line, at the resource's top level — NOT inside `template`):

```hcl
  lifecycle {
    ignore_changes = [template[0].containers[0].image]
  }
```

- [ ] **Step 2: Add the same `lifecycle` block to the `backend` service in `cloudrun.tf`**

Inside `resource "google_cloud_run_v2_service" "backend"`, before its `depends_on`:

```hcl
  lifecycle {
    ignore_changes = [template[0].containers[0].image]
  }
```

- [ ] **Step 3: Add the same `lifecycle` block to the `frontend` service in `cloudrun.tf`**

The `frontend` resource has no `depends_on`; add the block at the resource's top level (e.g. after the closing `}` of its `template` block, before the resource's final `}`):

```hcl
  lifecycle {
    ignore_changes = [template[0].containers[0].image]
  }
```

- [ ] **Step 4: Add `lifecycle` to the `ingest` job in `jobs.tf` (nested template path)**

Inside `resource "google_cloud_run_v2_job" "ingest"`, before its `depends_on`:

```hcl
  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image]
  }
```

Do NOT add a lifecycle block to the `migrate` job — it stays terraform-owned so it tracks `var.backend_image`.

- [ ] **Step 5: Format and validate**

Run:
```bash
cd garda-ai-deploy/terraform
terraform fmt
terraform validate 2>/dev/null || tofu validate
```
Expected: `fmt` leaves files formatted (reports the two changed files at most); `validate` prints `Success! The configuration is valid.` (If neither `terraform` nor `tofu` is installed, note it and fall back to `terraform fmt -check` skipped — but at minimum confirm the four `lifecycle` blocks are syntactically well-formed by eye.)

- [ ] **Step 6: Confirm exactly four lifecycle blocks, none on migrate**

Run: `cd garda-ai-deploy/terraform && grep -c "ignore_changes" cloudrun.tf jobs.tf`
Expected: `cloudrun.tf:3` and `jobs.tf:1`. Then `grep -n "migrate" jobs.tf` and confirm no `lifecycle`/`ignore_changes` appears within the migrate resource block.

- [ ] **Step 7: Commit**

```bash
cd garda-ai-deploy
git add terraform/cloudrun.tf terraform/jobs.tf
git commit -m "feat(tf): ignore image changes on Cloud Run services + ingest job

terraform provisions the resource; make deploy / gcloud own image rollout.
migrate job stays terraform-owned (tracks var.backend_image).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: `garda-ai-deploy` docs — runbook + stale-language sweep

**Files:**
- Modify: `garda-ai-deploy/docs/deploy/gcp-runbook.md`
- Possibly modify: other files under `garda-ai-deploy/docs/` if the grep in Step 3 finds stale auto-deploy language

- [ ] **Step 1: Update the CI/CD alternative in `gcp-runbook.md`**

Find the "Alternative: Let CI/CD do the build and push" text (around the Phase 2.4.2 section) that says pushing each service repo to `main` triggers `deploy.yml`. Replace it with a description of the two MANUAL routes:

```markdown
**Deploying a service (two equivalent manual routes — neither auto-fires):**

1. **Local (operator clones the repo):**
   ```bash
   cd garda-ai-<service>
   cp deploy.env.example deploy.env   # edit GCP_PROJECT / GCP_REGION (or export them)
   make deploy                        # build -> push -> gcloud run deploy
   ```
   Uses your own `gcloud auth login`. For the ingest job: `make deploy` then `make execute`.

2. **GitHub button:** Actions tab -> **deploy** -> **Run workflow** (`workflow_dispatch`).
   Requires the Workload Identity Federation setup (Phase 4). Never triggers on a merge to `main`.
```

- [ ] **Step 2: Add a "Deploy sequence" section to `gcp-runbook.md`**

Add this section (place it near the top of the deploy phases, or right after Phase 2 — implementer's judgment for best flow):

```markdown
## Deploy Sequence

**Cold start (first time, once):**
1. Foundation: `terraform apply -target=...` (VPC, Cloud SQL, Redis, Artifact Registry, secrets).
2. Seed first images: in each service repo, `make push` (build + push only — does NOT create the service).
3. Create services/jobs: full `terraform apply` (images now exist; services get their VPC/secret/ingress wiring).
4. Init data: `gcloud run jobs execute garda-migrate --region $REGION --wait`, then in `garda-ai-ingest` run `make execute` (seeds reference data).

**Routine redeploy (the common case):**
- In the changed service repo: `make deploy` (build -> push -> `gcloud run deploy` a new revision). No terraform, no other services touched.
- Breaking DB migration: run the `garda-migrate` job first. Because the migrate job stays terraform-owned, refresh it with `terraform apply` (re-resolves the backend `:latest` digest) before `gcloud run jobs execute garda-migrate --wait`.

`terraform` owns resource creation and wiring; `make deploy` owns image rollout. The terraform `lifecycle { ignore_changes = [...image] }` keeps `terraform apply` from reverting an operator's rollout.
```

- [ ] **Step 3: Sweep docs for stale auto-deploy language**

Run: `cd garda-ai-deploy && grep -rniE "push to main|on push to|auto-deploy|automatically deploy|triggers on push|on: *push" docs/ || echo "clean"`
For each hit, correct it to reflect the manual model (`workflow_dispatch` / `make deploy`). Common candidates: `docs/deploy/02-container.md`, `docs/deploy/01-context.md`. If a hit is describing `ci.yml` (lint/test on PRs — which legitimately still runs on push/PR), leave it. Re-run the grep until only legitimate CI references (or `clean`) remain.

- [ ] **Step 4: Commit**

```bash
cd garda-ai-deploy
git add docs/
git commit -m "docs: manual deploy runbook (make deploy + workflow_dispatch) and deploy sequence

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Final cross-repo verification

**Files:** none (verification only)

- [ ] **Step 1: Every deploy.yml is workflow_dispatch-only**

Run:
```bash
cd "/Users/thariqiskandar/Documents/Career/BI - OJK Hackathon 2025/repositories"
for r in garda-ai-backend garda-ai-scoring garda-ai-dashboard-web garda-ai-ingest; do
  echo "=== $r ==="
  python3 -c "import yaml; d=yaml.safe_load(open('$r/.github/workflows/deploy.yml')); t=d.get(True) or d.get('on'); print('trigger:', t); assert t=={'workflow_dispatch': None}, 'NOT dispatch-only'"
done
```
Expected: each prints `trigger: {'workflow_dispatch': None}` with no assertion error.

- [ ] **Step 2: Every service Makefile dry-runs to the right command**

Run:
```bash
cd "/Users/thariqiskandar/Documents/Career/BI - OJK Hackathon 2025/repositories"
for r in garda-ai-backend garda-ai-scoring garda-ai-dashboard-web; do
  echo "=== $r ==="; (cd $r && GCP_PROJECT=demo-proj GCP_REGION=asia-southeast1 make -n deploy | grep -E "gcloud run deploy")
done
(cd garda-ai-ingest && echo "=== garda-ai-ingest ===" && GCP_PROJECT=demo-proj GCP_REGION=asia-southeast1 make -n deploy | grep -E "gcloud run jobs deploy")
```
Expected: `garda-backend`, `garda-scoring`, `garda-frontend` service deploys; `garda-ingest` job deploy.

- [ ] **Step 2b: Every guard fails clean with no config**

Run:
```bash
cd "/Users/thariqiskandar/Documents/Career/BI - OJK Hackathon 2025/repositories"
for r in garda-ai-backend garda-ai-scoring garda-ai-dashboard-web garda-ai-ingest; do
  (cd $r && env -u GCP_PROJECT -u GCP_REGION make check-env >/dev/null 2>&1; echo "$r exit=$?")
done
```
Expected: every line ends `exit=1`.

- [ ] **Step 3: No `deploy.env` was committed; examples are present**

Run:
```bash
cd "/Users/thariqiskandar/Documents/Career/BI - OJK Hackathon 2025/repositories"
for r in garda-ai-backend garda-ai-scoring garda-ai-dashboard-web garda-ai-ingest; do
  echo "=== $r ==="
  git -C $r ls-files | grep -E "deploy.env" || echo "  (none tracked)"
done
```
Expected: each repo tracks `deploy.env.example` but NOT `deploy.env`.

- [ ] **Step 4: terraform lifecycle count**

Run: `cd "/Users/thariqiskandar/Documents/Career/BI - OJK Hackathon 2025/repositories/garda-ai-deploy/terraform" && grep -c ignore_changes cloudrun.tf jobs.tf`
Expected: `cloudrun.tf:3`, `jobs.tf:1`.

- [ ] **Step 5: All five repos clean, last commit authored correctly**

Run:
```bash
cd "/Users/thariqiskandar/Documents/Career/BI - OJK Hackathon 2025/repositories"
for r in garda-ai-backend garda-ai-scoring garda-ai-dashboard-web garda-ai-ingest garda-ai-deploy; do
  echo "=== $r ==="
  git -C $r status --porcelain | head -5
  git -C $r log -1 --format="  %an <%ae> — %s"
done
```
Expected: each repo clean (no uncommitted changes) and the last commit authored `Thariq Iskandar Zulkarnain M P <thariqiskandar9@gmail.com>`.

---

## Definition of Done

- Each of the four deployable repos has a root `Makefile` with `make deploy` (ingest also `make execute`), a committed `deploy.env.example`, and `deploy.env` gitignored.
- All four `deploy.yml` trigger ONLY on `workflow_dispatch` — no `push: main` auto-deploy remains.
- terraform: 3 services + the ingest job carry `ignore_changes` on the image; the migrate job does not; `validate` is green.
- The runbook describes both manual routes and the cold-start vs routine sequence; no stale auto-deploy language remains in docs (except legitimate `ci.yml` PR triggers).
- `garda-ai-sim` is untouched.
- Every commit authored as Thariq Iskandar Zulkarnain M P with the `Co-Authored-By: Claude` trailer; nothing pushed to any remote.
