from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from grafin_ai_scoring.api.middleware import ObservabilityMiddleware
from grafin_ai_scoring.api.routes import _provider
from grafin_ai_scoring.api.routes import router as scoring_router
from grafin_ai_scoring.config import get_settings
from grafin_ai_scoring.observability import REGISTRY, configure_logging

settings = get_settings()  # validates config (fails fast if GRAFIN_SCORING_TOKEN unset)
configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    _provider()  # build the scorer at startup: misconfig fails fast, scores.csv loads once
    yield


app = FastAPI(title="Grafin AI Scoring", version="0.1.0", lifespan=lifespan)
app.add_middleware(ObservabilityMiddleware)
app.include_router(scoring_router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> Response:
    return Response(content='{"status":"ready"}', media_type="application/json")


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
