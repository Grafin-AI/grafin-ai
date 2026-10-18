"""WebSocket relay test against a REAL uvicorn server.

The other WS tests use Starlette's in-process TestClient transport, which forwards
messages even with patterns that fail under uvicorn's real WebSocket transport
(that gap let a broken relay ship). This test runs the actual app under uvicorn in a
subprocess, connects a real ``websockets`` client, publishes an event to Redis, and
asserts it is pushed to the client — so the relay is exercised exactly as in production.
"""

import asyncio
import json
import os
import socket
import subprocess
import sys
import time

import pytest
from redis.asyncio import Redis

from grafin_ai_backend.realtime.channels import LIVE_EVENTS_CHANNEL
from grafin_ai_backend.security.tokens import create_access_token

websockets = pytest.importorskip("websockets")

_SECRET = "x" * 40  # >= 32 chars so the fail-closed validator is happy in any env


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _wait_until_listening(host: str, port: int, timeout: float = 25.0) -> None:
    deadline = time.monotonic() + timeout
    while True:
        try:
            _, writer = await asyncio.open_connection(host, port)
            writer.close()
            return
        except OSError:
            if time.monotonic() > deadline:
                raise TimeoutError(f"uvicorn did not start on {host}:{port}") from None
            await asyncio.sleep(0.3)


async def test_relay_streams_event_under_real_uvicorn(redis_url):
    port = _free_port()
    env = {
        **os.environ,
        "GRAFIN_REDIS_URL": redis_url,
        "GRAFIN_JWT_SECRET": _SECRET,
        "GRAFIN_ENV": "development",
        "GRAFIN_DATABASE_URL": "postgresql+asyncpg://x:x@localhost:5432/x",  # WS path never hits the DB
    }
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "grafin_ai_backend.main:app",
            "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning",
        ],
        env=env,
    )
    try:
        await _wait_until_listening("127.0.0.1", port)
        token = create_access_token(subject="1", role="analyst", secret=_SECRET, ttl_min=15)
        url = f"ws://127.0.0.1:{port}/api/v1/ws/live?token={token}"

        async with websockets.connect(url) as ws:
            # relay subscribes BEFORE sending "connected", so once we see it the
            # subscription is live and a subsequent publish must be delivered.
            hello = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            assert hello["type"] == "connected"

            pub = Redis.from_url(redis_url, decode_responses=True)
            event = {"seq": 42, "transaction_id": 7, "bank": "Bank BRI", "status": "blocked"}
            await pub.publish(LIVE_EVENTS_CHANNEL, json.dumps(event))
            await pub.aclose()

            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            assert msg["seq"] == 42
            assert msg["status"] == "blocked"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


async def test_relay_rejects_bad_token_under_real_uvicorn(redis_url):
    port = _free_port()
    env = {
        **os.environ,
        "GRAFIN_REDIS_URL": redis_url,
        "GRAFIN_JWT_SECRET": _SECRET,
        "GRAFIN_ENV": "development",
        "GRAFIN_DATABASE_URL": "postgresql+asyncpg://x:x@localhost:5432/x",
    }
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "grafin_ai_backend.main:app",
            "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning",
        ],
        env=env,
    )
    try:
        await _wait_until_listening("127.0.0.1", port)
        with pytest.raises(Exception):  # noqa: B017,PT011 - handshake rejected (1008/403)
            async with websockets.connect(f"ws://127.0.0.1:{port}/api/v1/ws/live?token=bad") as ws:
                await asyncio.wait_for(ws.recv(), timeout=5)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
