from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from garda_ai_backend.api.alerts import router as alerts_view_router
from garda_ai_backend.api.analytics import router as analytics_router
from garda_ai_backend.api.auth import router as auth_router
from garda_ai_backend.api.geo import router as geo_router
from garda_ai_backend.api.ingest import router as ingest_router
from garda_ai_backend.api.metrics import router as metrics_router
from garda_ai_backend.api.system import router as system_router
from garda_ai_backend.api.transactions import router as transactions_router
from garda_ai_backend.api.users_view import router as users_view_router
from garda_ai_backend.api.ws import router as ws_router
from garda_ai_backend.config import Settings, get_settings
from garda_ai_backend.db import _maker
from garda_ai_backend.observability import REGISTRY, configure_logging
from garda_ai_backend.redis_client import get_redis

settings = get_settings()
configure_logging(settings.log_level)


def configure_cors(app: FastAPI, settings: Settings) -> None:
    """GARDA_CORS_ORIGINS (comma-separated); empty = no CORS middleware (same-origin only).
    Bearer tokens, no cookies, so credentials stay off. WebSockets are not subject to
    CORS; /api/v1/ws/live authenticates with ?token=<access JWT>."""
    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_methods=["*"],
            allow_headers=["*"],
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # One pooled HTTP client shared across the app (e.g. the scoring client).
    app.state.http_client = httpx.AsyncClient()
    try:
        yield
    finally:
        await app.state.http_client.aclose()


app = FastAPI(title="Grafin AI Backend", version="0.1.0", lifespan=lifespan)
configure_cors(app, settings)
app.include_router(auth_router)
app.include_router(metrics_router)
app.include_router(analytics_router)
app.include_router(geo_router)
app.include_router(transactions_router)
app.include_router(users_view_router)
app.include_router(alerts_view_router)
app.include_router(system_router)
app.include_router(ws_router)
app.include_router(ingest_router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> Response:
    try:
        async with _maker()() as session:
            await session.execute(text("SELECT 1"))
        await get_redis().ping()
        return Response(content='{"status":"ready"}', media_type="application/json")
    except Exception:
        return Response(
            content='{"status":"not-ready"}', media_type="application/json", status_code=503
        )


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
