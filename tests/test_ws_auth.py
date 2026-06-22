from garda_ai_backend.api.ws_auth import authenticate_ws_token
from garda_ai_backend.realtime.channels import LIVE_EVENTS_CHANNEL
from garda_ai_backend.security.tokens import create_access_token, create_refresh_token

S = "test-secret"


def test_channel_constant_is_stable():
    assert LIVE_EVENTS_CHANNEL == "garda:events:live"


def test_valid_access_token():
    t = create_access_token(subject="3", role="admin", secret=S, ttl_min=15)
    u = authenticate_ws_token(t, S)
    assert u is not None
    assert u.id == 3
    assert u.role == "admin"


def test_rejects_empty():
    assert authenticate_ws_token("", S) is None


def test_rejects_garbage():
    assert authenticate_ws_token("not-a-jwt", S) is None


def test_rejects_wrong_secret():
    t = create_access_token(subject="3", role="admin", secret=S, ttl_min=15)
    assert authenticate_ws_token(t, "other-secret") is None


def test_rejects_refresh_token():
    t = create_refresh_token(subject="3", secret=S, ttl_days=7)
    assert authenticate_ws_token(t, S) is None
