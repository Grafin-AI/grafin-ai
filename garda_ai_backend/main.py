from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from garda_ai_backend.api.analytics import router as analytics_router
from garda_ai_backend.api.auth import router as auth_router
from garda_ai_backend.api.geo import router as geo_router
from garda_ai_backend.api.metrics import router as metrics_router
from garda_ai_backend.api.sim import router as sim_router
from garda_ai_backend.api.transactions import router as transactions_router
from garda_ai_backend.config import get_settings
from garda_ai_backend.db import _maker
from garda_ai_backend.observability import REGISTRY, configure_logging
from garda_ai_backend.redis_client import get_redis

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(title="Garda AI Backend", version="0.1.0")
app.include_router(auth_router)
app.include_router(sim_router)
app.include_router(metrics_router)
app.include_router(analytics_router)
app.include_router(geo_router)
app.include_router(transactions_router)


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
