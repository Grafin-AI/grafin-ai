# Deploy — Per-Service CI/CD + nginx Templating + Docs (Phase 6 ③④)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Give each deployable repo its own CI + a GCP deploy workflow, templatize the frontend nginx upstream so one image works locally and in the cloud, delete the legacy centralized CI, and update the docs (C4 + GCP runbook + README + pipeline purge).

**Architecture:** Each service repo owns `.github/workflows/ci.yml` (test/lint) and `deploy.yml` (build → Artifact Registry → Cloud Run, via Workload Identity Federation — no long-lived keys). The frontend nginx `proxy_pass` becomes `${BACKEND_URL}`, injected via the nginx image's env-template mechanism (local compose sets it to `http://backend:8000`; Terraform sets it to the backend Cloud Run URL).

**Verification bar:** workflows parse cleanly (a YAML/actionlint check); the frontend image builds and serves locally with the templated nginx; docs updated; no pipeline residue. The workflows *running* against real GCP is the operator's step (they set the repo WIF secrets).

**Spec:** `docs/superpowers/specs/2026-06-25-deploy-split-design.md`

**Author note:** commit in each repo with that repo's local git author already set to Thariq Iskandar Zulkarnain M P / thariqiskandar9@gmail.com. Verify with `git config user.email` before committing in each repo; the frontend + backend + scoring + ingest repos should already be set from prior phases — if any shows a different email, set it first.

---

## Task 1: Templatize the frontend nginx upstream

**Files:**
- Rename/modify: `garda-ai-dashboard-web/nginx.conf` → `garda-ai-dashboard-web/nginx.conf.template`
- Modify: `garda-ai-dashboard-web/Dockerfile`
- Modify: `garda-ai-deploy/docker-compose.yml` (add `BACKEND_URL` to the frontend service)

- [ ] **Step 1: Create `nginx.conf.template` (from the current `nginx.conf`, with `${BACKEND_URL}`)**

```nginx
server {
    listen 8080;
    listen [::]:8080;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    # REST → backend
    location /api/ {
        proxy_pass ${BACKEND_URL};
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket live feed → backend (upgrade headers)
    location /api/v1/ws/ {
        proxy_pass ${BACKEND_URL};
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 3600s;
    }

    # security headers
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options DENY;
    add_header Referrer-Policy strict-origin-when-cross-origin;

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```
Delete the old `nginx.conf`. (The `nginx:alpine` image runs `envsubst` only over env-defined vars, so `${BACKEND_URL}` is substituted while nginx's own `$host`/`$http_upgrade`/`$scheme` are preserved.)

- [ ] **Step 2: Update the frontend `Dockerfile` production stage**

Replace the nginx-conf copy line:
```dockerfile
COPY nginx.conf /etc/nginx/conf.d/default.conf
```
with:
```dockerfile
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
```
(The stock nginx entrypoint renders `/etc/nginx/templates/*.template` → `/etc/nginx/conf.d/` at startup, substituting `${BACKEND_URL}`.)

- [ ] **Step 3: Set `BACKEND_URL` for the frontend in local compose**

In `garda-ai-deploy/docker-compose.yml`, add an `environment` block to the `frontend` service:
```yaml
  frontend:
    build: { context: ../garda-ai-dashboard-web }
    environment:
      BACKEND_URL: http://backend:8000
    depends_on: [backend]
    ports: ["8080:8080"]
```

- [ ] **Step 4: Build + serve locally to confirm the template renders**

Run:
```bash
docker build -t garda-frontend-test ../garda-ai-dashboard-web  # from garda-ai-deploy, adjust path as needed
docker run --rm -e BACKEND_URL=http://example:8000 garda-frontend-test sh -c "cat /etc/nginx/conf.d/default.conf" | grep -E "proxy_pass"
```
Expected: the `proxy_pass http://example:8000;` lines (BACKEND_URL substituted), nginx `$host` etc. intact. If Docker isn't available, SKIP and note it; the template + Dockerfile edits are the required change.

- [ ] **Step 5: Commit (in each repo)**

Frontend repo:
```bash
cd garda-ai-dashboard-web
git add nginx.conf.template Dockerfile && git rm nginx.conf
git commit -m "feat: templatize nginx upstream via BACKEND_URL for local+cloud"
```
Deploy repo:
```bash
cd ../garda-ai-deploy
git add docker-compose.yml
git commit -m "chore: set BACKEND_URL for the frontend in local compose"
```

---

## Task 2: Add CI to backend + frontend (they lack `.github/workflows`)

**Files:**
- Create: `garda-ai-backend/.github/workflows/ci.yml`, `garda-ai-dashboard-web/.github/workflows/ci.yml`

- [ ] **Step 1: Backend CI (uv + ruff + pytest; testcontainers works on ubuntu-latest Docker)**

`garda-ai-backend/.github/workflows/ci.yml`:
```yaml
name: ci
on:
  push:
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        run: pip install uv
      - name: Sync
        run: uv sync --frozen
      - name: Lint (changed scope)
        run: uv run ruff check garda_ai_backend || true   # repo has known pre-existing ruff debt; do not fail CI on it
      - name: Test
        env:
          GARDA_JWT_SECRET: ci-secret-at-least-32-chars-long-xxxx
          GARDA_SCORING_URL: http://scoring:8000
          GARDA_SCORING_TOKEN: ci-scoring
          GARDA_INGEST_TOKEN: ci-ingest-token-16chars
        run: uv run pytest -q
```
> Note: the `|| true` on ruff reflects the repo's pre-existing lint debt documented in earlier phases; keep tests as the hard gate. If the debt has since been cleaned, drop the `|| true`.

- [ ] **Step 2: Frontend CI (npm + vitest + build)**

`garda-ai-dashboard-web/.github/workflows/ci.yml`:
```yaml
name: ci
on:
  push:
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - name: Install
        run: npm install
      - name: Test
        run: npm test
      - name: Build
        run: npm run build
```

- [ ] **Step 3: Commit (each repo)**

```bash
cd garda-ai-backend && git add .github/workflows/ci.yml && git commit -m "ci: add backend test/lint workflow"
cd ../garda-ai-dashboard-web && git add .github/workflows/ci.yml && git commit -m "ci: add frontend test/build workflow"
```

---

## Task 3: Add a GCP deploy workflow to the 4 deployable repos

**Files:**
- Create: `.github/workflows/deploy.yml` in `garda-ai-backend`, `garda-ai-dashboard-web`, `garda-ai-scoring`, `garda-ai-ingest`

- [ ] **Step 1: Service deploy workflow template (backend / scoring / frontend)**

Use this shape, changing `IMAGE`, `SERVICE`, and the build context per repo. Example for **backend**:
```yaml
name: deploy
on:
  push:
    branches: [main]
env:
  REGION: ${{ vars.GCP_REGION }}
  PROJECT: ${{ vars.GCP_PROJECT }}
  IMAGE: ${{ vars.GCP_REGION }}-docker.pkg.dev/${{ vars.GCP_PROJECT }}/garda/backend
  SERVICE: garda-backend
jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write   # Workload Identity Federation
    steps:
      - uses: actions/checkout@v4
      - id: auth
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ secrets.GCP_WIF_PROVIDER }}
          service_account: ${{ secrets.GCP_DEPLOYER_SA }}
      - uses: google-github-actions/setup-gcloud@v2
      - name: Configure Docker for Artifact Registry
        run: gcloud auth configure-docker ${{ env.REGION }}-docker.pkg.dev --quiet
      - name: Build & push
        run: |
          docker build -t "$IMAGE:${{ github.sha }}" -t "$IMAGE:latest" .
          docker push "$IMAGE:${{ github.sha }}"
          docker push "$IMAGE:latest"
      - name: Deploy to Cloud Run
        run: gcloud run deploy "$SERVICE" --image "$IMAGE:${{ github.sha }}" --region "$REGION" --quiet
```
- **scoring**: `IMAGE=.../garda/scoring`, `SERVICE=garda-scoring`.
- **frontend**: `IMAGE=.../garda/frontend`, `SERVICE=garda-frontend`.

- [ ] **Step 2: Job deploy workflow for `ingest`** (a Cloud Run **Job**, not a service)

`garda-ai-ingest/.github/workflows/deploy.yml` — same auth/build/push, but the deploy step:
```yaml
      - name: Deploy Cloud Run Job
        run: gcloud run jobs deploy garda-ingest --image "$IMAGE:${{ github.sha }}" --region "$REGION" --quiet
```
with `IMAGE=.../garda/ingest`.

- [ ] **Step 3: Validate workflow syntax**

If `actionlint` is available: `actionlint` across the changed workflow files. Otherwise a YAML parse check:
```bash
for f in garda-ai-backend/.github/workflows/deploy.yml garda-ai-dashboard-web/.github/workflows/deploy.yml garda-ai-scoring/.github/workflows/deploy.yml garda-ai-ingest/.github/workflows/deploy.yml; do python -c "import yaml,sys; yaml.safe_load(open('$f')); print('ok', '$f')"; done
```
Expected: `ok` for each.

- [ ] **Step 4: Commit (each repo)**

```bash
cd garda-ai-backend && git add .github/workflows/deploy.yml && git commit -m "ci: GCP Cloud Run deploy workflow (WIF)"
cd ../garda-ai-dashboard-web && git add .github/workflows/deploy.yml && git commit -m "ci: GCP Cloud Run deploy workflow (WIF)"
cd ../garda-ai-scoring && git add .github/workflows/deploy.yml && git commit -m "ci: GCP Cloud Run deploy workflow (WIF)"
cd ../garda-ai-ingest && git add .github/workflows/deploy.yml && git commit -m "ci: GCP Cloud Run Job deploy workflow (WIF)"
```

---

## Task 4: Delete legacy centralized CI + purge pipeline residue (deploy repo)

**Files:**
- Delete: `garda-ai-deploy/ci/backend.yml`, `ci/frontend.yml`, `ci/pipeline.yml`

- [ ] **Step 1: Remove the legacy CI dir (now superseded by per-repo workflows)**

```bash
cd garda-ai-deploy && git rm -r ci/
```

- [ ] **Step 2: Scan for any remaining pipeline residue in the deploy repo**

Run: `grep -rniE "garda-ai-pipeline|garda-etl|garda-replay|\betl\b|\breplay\b|sim_state" garda-ai-deploy --include="*.yml" --include="*.yaml" --include="*.md" --include="Makefile" --include="*.tf" | grep -v "docs/superpowers/specs" | grep -v "docs/superpowers/plans" || echo "clean"`
Expected: `clean` (historical specs/plans may mention them as record — those are excluded).

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "chore: delete legacy centralized CI (moved into per-service repos)"
```

---

## Task 5: Docs — C4 container diagram, GCP runbook, README

**Files:**
- Modify: `garda-ai-deploy/docs/c4/02-container.md`
- Create: `garda-ai-deploy/docs/deploy/gcp-runbook.md`
- Modify: `garda-ai-deploy/README.md`

- [ ] **Step 1: Update `docs/c4/02-container.md`** to the GCP Cloud Run topology: public `backend` + `frontend` (nginx), **internal** `scoring`, `migrate` + `ingest` Cloud Run Jobs, Cloud SQL + Memorystore (private via VPC connector), Secret Manager, Artifact Registry; `garda-ai-sim` shown as an **external local producer** posting to the public backend `/ingest`. Remove the pipeline `etl`/`replay` containers. Note the local-compose variant mirrors this minus the managed services.

- [ ] **Step 2: Create `docs/deploy/gcp-runbook.md`** — the operator checklist (the "only you can do" steps):
  1. Create a GCP project; enable billing.
  2. `terraform/` — provide `terraform.tfvars` (project/region/domain/images) + secrets via `TF_VAR_*` env or a gitignored `*.auto.tfvars`; configure a **remote state backend** (GCS bucket, restricted) because state holds secret values.
  3. `terraform init && terraform apply` (enables APIs, provisions network/DB/Redis/registry/secrets/services/jobs).
  4. Set up **Workload Identity Federation** for the 4 repos; set repo `vars` (`GCP_PROJECT`, `GCP_REGION`) + `secrets` (`GCP_WIF_PROVIDER`, `GCP_DEPLOYER_SA`).
  5. Push images (CI `deploy.yml` on push to `main`, or manual build/push).
  6. Run the deploy-init jobs: `gcloud run jobs execute garda-migrate` then `gcloud run jobs execute garda-ingest`.
  7. Map the domain: create the DNS records from `terraform output domain_dns_app/api`.
  8. Run the sim locally: `GARDA_INGEST_URL=https://api.<domain>/api/v1/ingest GARDA_INGEST_TOKEN=... uv run garda-sim`.

- [ ] **Step 3: Update `README.md`** — local-dev quickstart for the new compose (`cp .env.example .env`, set secrets/tokens, `make up`; `make sim` to stream; `make obs` for Prometheus/Grafana), and a pointer to `docs/deploy/gcp-runbook.md` for cloud. Remove any pipeline/replay mentions.

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "docs: C4 container (GCP topology), GCP runbook, README refresh"
```

---

## Definition of Done

- Frontend nginx upstream is `${BACKEND_URL}`-templated; the image builds and serves with it; local compose sets `BACKEND_URL=http://backend:8000`.
- backend + frontend have `.github/workflows/ci.yml`; all 4 deployable repos have a `deploy.yml` (services via `gcloud run deploy`, ingest via `gcloud run jobs deploy`), using WIF (no long-lived keys); workflows parse cleanly.
- Legacy `garda-ai-deploy/ci/` deleted; no pipeline residue in deploy config (specs/plans excluded).
- Docs: C4 `02-container` shows the GCP topology; `docs/deploy/gcp-runbook.md` exists with the operator steps; README refreshed.
- All commits authored as Thariq Iskandar Zulkarnain M P with the `Co-Authored-By: Claude` trailer, in each respective repo.

## Out of scope (operator's step)

Creating the GCP project + WIF, setting repo secrets/vars, running the deploy workflows against real GCP, and DNS record creation. This plan delivers the authored, syntactically-valid CI/CD + templated image + runbook.
```
