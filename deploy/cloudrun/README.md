# Cloud Run + Firebase deployment (set `PROJECT_ID` to your GCP project; region `asia-southeast2`)

Secrets are never committed. Create `api-env.yaml` and `scoring-env.yaml` locally (keys below).

## 1. Data and storage
```bash
gcloud sql instances create grafin-pg --database-version=POSTGRES_16 --region=asia-southeast2 \
  --edition=ENTERPRISE --tier=db-custom-2-8192 --storage-size=20 --storage-auto-increase
gcloud sql databases create <db> --instance=grafin-pg
gcloud sql users create <db-user> --instance=grafin-pg --password="$DB_PASSWORD"
gcloud sql import sql grafin-pg gs://<bucket>/<dump>.sql.gz --database=<db> --user=<db-user>
gcloud firestore databases create --location=asia-southeast2 --type=firestore-native
gcloud artifacts repositories create grafin --repository-format=docker --location=asia-southeast2
```

## 2. Images (linux/amd64)
The scoring image bakes in the exported model scores (`training/runs/<run>/scores`) by
appending `scoring.Dockerfile.append` to `scoring/Dockerfile`.
```bash
REG=asia-southeast2-docker.pkg.dev/$PROJECT_ID/grafin
docker buildx build --platform linux/amd64 -t $REG/backend:v1 --push backend
docker buildx build --platform linux/amd64 -t $REG/scoring:v1 --push <scoring context with scores/>
```

## 3. Cloud Run: one public service, private sidecars
```bash
gcloud run deploy grafin-api --region asia-southeast2 \
  --add-cloudsql-instances $PROJECT_ID:asia-southeast2:grafin-pg \
  --min-instances 1 --max-instances 1 --no-cpu-throttling --timeout 3600 --execution-environment gen2 \
  --container backend --image $REG/backend:v1 --port 8000 --env-vars-file api-env.yaml \
      --memory 2Gi --cpu 2 --depends-on scoring,redis \
  --container scoring --image $REG/scoring:v1 --env-vars-file scoring-env.yaml --command sh \
      --args="-c,uv run --no-sync uvicorn grafin_ai_scoring.api.app:app --host 0.0.0.0 --port 8001" \
      --memory 2Gi --cpu 1 --startup-probe tcpSocket.port=8001,periodSeconds=5,failureThreshold=60 \
  --container redis --image mirror.gcr.io/library/redis:7-alpine --memory 512Mi --cpu 0.5 \
      --startup-probe tcpSocket.port=6379,periodSeconds=2,failureThreshold=30
gcloud run services add-iam-policy-binding grafin-api --region asia-southeast2 \
  --member=allUsers --role=roles/run.invoker
```
The runtime service account needs `roles/cloudsql.client`, `roles/datastore.user`,
`roles/logging.logWriter`, `roles/artifactregistry.reader`.

`api-env.yaml` keys: `GRAFIN_DATABASE_URL` (`postgresql+asyncpg://<db-user>:<pw>@/<db>?host=/cloudsql/<connection>`),
`GRAFIN_REDIS_URL=redis://localhost:6379/0`, `GRAFIN_SCORING_URL=http://localhost:8001`,
`GRAFIN_JWT_SECRET`, `GRAFIN_SCORING_TOKEN`, `GRAFIN_INGEST_TOKEN`, `GRAFIN_ENV=production`,
`GRAFIN_LLM_PROVIDER=gemini`, `GRAFIN_LLM_MODEL=gemini-3.8-flash`, `GRAFIN_LLM_API_KEY`,
`GRAFIN_LLM_TIMEOUT_S=60`, `GRAFIN_MODEL_NAME`, `GRAFIN_EXPLANATION_STORE=firestore`,
`GRAFIN_FIRESTORE_PROJECT=<project-id>`, `GRAFIN_CORS_ORIGINS=https://<site>.web.app,https://<site>.firebaseapp.com`.
`scoring-env.yaml`: `GRAFIN_SCORING_TOKEN`, `GRAFIN_SCORER=precomputed`, `GRAFIN_SCORES_PATH=/scores/scores.csv`.

## 4. Dashboard on Firebase Hosting
```bash
cd dashboard-web
VITE_API_BASE_URL=https://<grafin-api-url>/api/v1 \
VITE_WS_URL=wss://<grafin-api-host>/api/v1/ws/live npx vite build --outDir ../deploy/cloudrun/dist
cd ../deploy/cloudrun && npx firebase-tools deploy --only hosting --project <firebase-project>
```
