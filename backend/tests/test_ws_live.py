import json

import pytest
import redis as sync_redis
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from grafin_ai_backend.api import deps
from grafin_ai_backend.realtime.channels import LIVE_EVENTS_CHANNEL
from grafin_ai_backend.redis_client import build_redis
from grafin_ai_backend.security.tokens import create_access_token


def _app(redis_url):
    from grafin_ai_backend.main import app
    app.dependency_overrides[deps.get_redis_dep] = lambda: build_redis(redis_url)
    return app


def test_ws_rejects_bad_token(redis_url):
    app = _app(redis_url)
    try:
        with TestClient(app) as tc:
            with pytest.raises(WebSocketDisconnect):
                with tc.websocket_connect("/api/v1/ws/live?token=bad") as ws:
                    ws.receive_json()
    finally:
        app.dependency_overrides.clear()


def test_ws_relays_published_event(redis_url):
    app = _app(redis_url)
    token = create_access_token(subject="1", role="analyst", secret="test-secret", ttl_min=15)
    try:
        with TestClient(app) as tc:
            with tc.websocket_connect(f"/api/v1/ws/live?token={token}") as ws:
                assert ws.receive_json()["type"] == "connected"
                pub = sync_redis.from_url(redis_url)
                event = {"seq": 5, "bank": "Bank BRI", "status": "blocked", "fraud_score": 0.95}
                pub.publish(LIVE_EVENTS_CHANNEL, json.dumps(event))
                msg = ws.receive_json()
                assert msg["seq"] == 5
                assert msg["status"] == "blocked"
                pub.close()
    finally:
        app.dependency_overrides.clear()
