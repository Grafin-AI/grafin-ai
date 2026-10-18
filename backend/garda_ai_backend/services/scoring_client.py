import asyncio

import httpx


class ScoringUnavailable(Exception):
    """The scoring service could not be reached / rejected the batch. Maps to HTTP 503."""


class ScoringClient:
    """Thin client for garda-ai-scoring's POST /v1/score. Retries transient failures."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        token: str,
        *,
        retries: int = 2,
        timeout_s: float = 5.0,
    ) -> None:
        self._client = client
        self._url = base_url.rstrip("/") + "/v1/score"
        self._token = token
        self._retries = retries
        self._timeout = timeout_s

    async def score(
        self, transactions: list[dict], correlation_id: str | None = None
    ) -> list[dict]:
        headers = {"Authorization": f"Bearer {self._token}"}
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id
        last_exc: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                resp = await self._client.post(
                    self._url,
                    json={"transactions": transactions},
                    headers=headers,
                    timeout=self._timeout,
                )
            except httpx.TransportError as exc:  # connect/read timeouts, conn errors
                last_exc = exc
            else:
                if resp.status_code < 400:
                    try:
                        return list(resp.json()["results"])
                    except (ValueError, KeyError, TypeError) as exc:
                        raise ScoringUnavailable("scoring returned a malformed response") from exc
                if resp.status_code < 500:
                    # A 4xx is a contract/auth problem — not transient; do not retry.
                    raise ScoringUnavailable(
                        f"scoring rejected batch: HTTP {resp.status_code}"
                    )
                last_exc = httpx.HTTPStatusError(
                    "scoring 5xx", request=resp.request, response=resp
                )
            if attempt < self._retries:
                await asyncio.sleep(0.1 * (2**attempt))  # 0.1s, 0.2s backoff
        raise ScoringUnavailable("scoring service unavailable after retries") from last_exc
