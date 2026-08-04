import asyncio
from typing import NamedTuple

import httpx


class IngestSummary(NamedTuple):
    ingested: int
    duplicate: int


class IngestError(Exception):
    """The backend rejected the batch (4xx: bad token / contract). Not retryable."""


class IngestUnavailable(Exception):
    """The backend was unreachable / returned 5xx after retries."""


class IngestClient:
    """Thin client for the backend POST /api/v1/ingest. Retries transient failures."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        url: str,
        token: str,
        *,
        retries: int = 3,
        timeout_s: float = 30.0,
    ) -> None:
        self._client = client
        self._url = url
        self._token = token
        self._retries = retries
        self._timeout = timeout_s

    async def send(
        self, txns: list[dict[str, object]], *, correlation_id: str
    ) -> IngestSummary:
        headers = {
            "Authorization": f"Bearer {self._token}",
            "X-Correlation-ID": correlation_id,
        }
        last_exc: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                resp = await self._client.post(
                    self._url,
                    json={"transactions": txns},
                    headers=headers,
                    timeout=self._timeout,
                )
            except httpx.TransportError as exc:  # connect/read timeouts, connection errors
                last_exc = exc
            else:
                if resp.status_code < 400:
                    try:
                        results = list(resp.json()["results"])
                    except (ValueError, KeyError, TypeError) as exc:
                        raise IngestUnavailable("ingest returned a malformed response") from exc
                    ingested = sum(1 for r in results if r.get("ingested"))
                    return IngestSummary(ingested=ingested, duplicate=len(results) - ingested)
                if resp.status_code < 500:
                    # A 4xx is a contract/auth problem — not transient; do not retry.
                    raise IngestError(f"ingest rejected batch: HTTP {resp.status_code}")
                last_exc = httpx.HTTPStatusError(
                    "ingest 5xx", request=resp.request, response=resp
                )
            if attempt < self._retries:
                await asyncio.sleep(0.5 * (2**attempt))  # 0.5s, 1s, 2s backoff
        raise IngestUnavailable("ingest unavailable after retries") from last_exc
