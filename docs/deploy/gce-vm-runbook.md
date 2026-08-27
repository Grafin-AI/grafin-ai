# Deploying to a single GCE VM (pulled images)

The simplest path: one Compute Engine VM running `docker-compose.prod.yml`, with every
service pulled as a pre-built image from Artifact Registry. Postgres and Redis run as
containers on the same VM.

For the managed alternative (Cloud Run + Cloud SQL + Memorystore, via Terraform) see
`gcp-runbook.md` — this file is the "get it up quickly" route.

**What runs where:** the dashboard, backend, scoring service, Postgres and Redis all run
on the VM. The **simulator stays on your laptop** and streams to the VM over the internet.

---

## 0. Prerequisites

```bash
gcloud auth login
gcloud config set project <YOUR_PROJECT_ID>
export PROJECT=$(gcloud config get-value project)
export REGION=asia-southeast2          # Jakarta; use whatever is closest
export ZONE=${REGION}-a
```

Enable the APIs (once per project):

```bash
gcloud services enable compute.googleapis.com artifactregistry.googleapis.com
```

---

## 1. Create the image registry

```bash
gcloud artifacts repositories create garda \
  --repository-format=docker \
  --location=${REGION} \
  --description="Garda AI service images"

export REGISTRY=${REGION}-docker.pkg.dev/${PROJECT}/garda
echo $REGISTRY     # note this — it goes in the VM's .env
```

---

## 2. Build and push the four images

**Architecture matters.** GCE VMs are `linux/amd64`. An Apple Silicon Mac builds
`linux/arm64` by default, and those images die on the VM with `exec format error`. The
script forces `--platform linux/amd64`.

```bash
gcloud auth configure-docker ${REGION}-docker.pkg.dev --quiet

cd garda-ai-deploy
./scripts/build-and-push.sh ${REGISTRY} v1
```

Builds and pushes `garda-ai-backend`, `garda-ai-scoring`, `garda-ai-ingest`, and
`garda-ai-frontend`, each tagged `v1` and `latest`.

Cross-building under emulation is slow (often 5–15 minutes total). If that drags, build
natively in the cloud instead — from each service repo:

```bash
gcloud builds submit --tag ${REGISTRY}/garda-ai-backend:v1 .
```

Verify what landed:

```bash
gcloud artifacts docker images list ${REGISTRY}
```

---

## 3. Create the VM

`e2-standard-2` (2 vCPU / 8 GB) is a comfortable fit for the whole stack. `e2-medium`
(4 GB) works but leaves little headroom once Postgres has a few million rows.

```bash
gcloud compute instances create garda-demo \
  --zone=${ZONE} \
  --machine-type=e2-standard-2 \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --boot-disk-size=50GB \
  --boot-disk-type=pd-balanced \
  --scopes=https://www.googleapis.com/auth/cloud-platform \
  --tags=garda-demo
```

`--scopes=cloud-platform` is what lets the VM pull from Artifact Registry without a key
file. Open the dashboard port:

```bash
gcloud compute firewall-rules create garda-allow-http \
  --allow=tcp:80 \
  --target-tags=garda-demo \
  --description="Garda dashboard"
```

Get the public address:

```bash
gcloud compute instances describe garda-demo --zone=${ZONE} \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)'
```

---

## 4. Install Docker on the VM

```bash
gcloud compute ssh garda-demo --zone=${ZONE}
```

Then, on the VM:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
exit                      # log out and back in so the group takes effect
```

Reconnect, then let Docker authenticate to Artifact Registry:

```bash
gcloud compute ssh garda-demo --zone=${ZONE}
gcloud auth configure-docker ${REGION}-docker.pkg.dev --quiet
```

---

## 5. Upload the bundle

From your laptop:

```bash
gcloud compute scp garda-ai-gce-bundle.zip garda-demo:~ --zone=${ZONE}
gcloud compute ssh garda-demo --zone=${ZONE}
```

On the VM:

```bash
sudo apt-get update && sudo apt-get install -y unzip
unzip garda-ai-gce-bundle.zip -d garda && cd garda
```

The bundle carries `docker-compose.prod.yml`, `.env.prod.example`, this runbook, and
`data/HI-Small_accounts.csv` (the reference data the seed job loads).

---

## 6. Configure and start

```bash
cp .env.prod.example .env
head -c 48 /dev/urandom | base64      # run a few times for the secrets
nano .env                             # fill in GARDA_REGISTRY and every CHANGE-ME
docker compose -f docker-compose.prod.yml up -d
```

Boot order is automatic: postgres/redis → scoring → backend (runs `alembic upgrade head`
and seeds the admin user, then serves) → ingest (one-shot reference load) → frontend.

Watch it come up:

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs ingest --tail=20   # expect seed.done, Exited (0)
```

---

## 7. Verify

Open `http://<VM_PUBLIC_IP>/` and sign in with `admin@garda.local` / `admin`.

The dashboard will be empty of transactions — reference data only. That is expected.

---

## 8. Load history and run the demo, from your laptop

The dashboard's nginx proxies `/api/` and `/api/v1/ws/` to the backend inside the compose
network, so the simulator can reach the ingest endpoint through port 80 — the backend
itself never needs to be exposed.

```bash
cd garda-ai-sim
export GARDA_INGEST_URL=http://<VM_PUBLIC_IP>/api/v1/ingest
export GARDA_INGEST_TOKEN=<the GARDA_INGEST_TOKEN from the VM's .env>
export GARDA_DATA_DIR=../garda-ai-data/HI-Small

# history: six days (2025-09-03..08), unpaced
GARDA_SKIP=1869370 GARDA_LIMIT=2345075 GARDA_MAX_GAP_S=0 GARDA_BATCH_SIZE=1000 uv run garda-sim

# live: 2025-09-09, one dataset-hour per wall-minute
GARDA_SKIP=4214445 GARDA_SPEED=60 GARDA_BATCH_SIZE=100 uv run garda-sim
```

Seeding over the internet is slower than locally — every batch is a round trip to GCP
rather than to localhost. Expect roughly 10–20 minutes for the six-day history depending
on your uplink.

---

## Security: read before showing anyone

**This runs over plain HTTP.** The ingest token, the login credentials, and the JWT all
cross the internet in the clear, and the dashboard is reachable by anyone who finds the
IP. That is acceptable for a short private demo; it is not acceptable for anything real.

Minimum hardening before a public demo:

1. **Change the seeded admin password.** `admin@garda.local` / `admin` is created on every
   boot by the backend's entrypoint. Anyone who reaches the IP can sign in.
2. **Restrict the firewall** to your own address rather than the whole internet:
   ```bash
   gcloud compute firewall-rules update garda-allow-http --source-ranges=<YOUR_IP>/32
   ```
3. **Add TLS** if it will live longer than a demo — a domain plus a reverse proxy with
   Let's Encrypt, or put the VM behind an HTTPS load balancer.

---

## Operating it

```bash
# logs
docker compose -f docker-compose.prod.yml logs -f --tail=100

# ship a new image version
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d

# where did the replay get to (use as the next GARDA_SKIP)
docker compose -f docker-compose.prod.yml exec -T postgres \
  psql -U garda -d garda -tAc 'select max(id) from transactions'

# stop (keeps data) / wipe entirely
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml down -v

# delete the VM when finished — this is what stops the billing
gcloud compute instances delete garda-demo --zone=${ZONE}
```

## Costs

An `e2-standard-2` with a 50 GB balanced disk runs roughly USD 50–60/month if left on
around the clock. For demo use, stop it when idle (`gcloud compute instances stop
garda-demo --zone=${ZONE}`) — a stopped instance bills only for the disk.
