import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from garda_ai_scoring.observability import REQUEST_COUNT, REQUEST_DURATION

_logger = structlog.get_logger()


class ObservabilityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        cid = (
            request.headers.get("x-correlation-id")
            or request.headers.get("x-request-id")
            or uuid.uuid4().hex
        )
        structlog.contextvars.bind_contextvars(correlation_id=cid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            elapsed = time.perf_counter() - start
            structlog.contextvars.clear_contextvars()

        route = request.scope.get("route")
        endpoint = getattr(route, "path", None) or "unmatched"
        REQUEST_COUNT.labels(endpoint, request.method, str(response.status_code)).inc()
        REQUEST_DURATION.labels(endpoint, request.method).observe(elapsed)
        response.headers["X-Correlation-ID"] = cid
        _logger.info(
            "request",
            method=request.method,
            endpoint=endpoint,
            status_code=response.status_code,
            duration_ms=round(elapsed * 1000, 2),
        )
        return response
