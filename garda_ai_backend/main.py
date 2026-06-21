from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from garda_ai_backend.config import get_settings
from garda_ai_backend.db import _maker
from garda_ai_backend.observability import REGISTRY, configure_logging

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(title="Garda AI Backend", version="0.1.0")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> Response:
    try:
        async with _maker()() as session:
            await session.execute(text("SELECT 1"))
        return Response(content='{"status":"ready"}', media_type="application/json")
    except Exception:
        return Response(
            content='{"status":"not-ready"}', media_type="application/json", status_code=503
        )


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
