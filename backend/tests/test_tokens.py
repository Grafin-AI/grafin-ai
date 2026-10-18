import pytest

from grafin_ai_backend.security.tokens import (
    InvalidToken,
    create_access_token,
    create_refresh_token,
    decode_token,
)

SECRET = "test-secret"


def test_access_token_roundtrip():
    token = create_access_token(subject="7", role="analyst", secret=SECRET, ttl_min=15)
    claims = decode_token(token, secret=SECRET)
    assert claims["sub"] == "7"
    assert claims["role"] == "analyst"
    assert claims["type"] == "access"


def test_refresh_token_has_jti_and_type():
    token = create_refresh_token(subject="7", secret=SECRET, ttl_days=7)
    claims = decode_token(token, secret=SECRET)
    assert claims["type"] == "refresh"
    assert "jti" in claims


def test_decode_rejects_bad_signature():
    token = create_access_token(subject="7", role="analyst", secret=SECRET, ttl_min=15)
    with pytest.raises(InvalidToken):
        decode_token(token, secret="other-secret")


def test_decode_rejects_expired():
    token = create_access_token(subject="7", role="analyst", secret=SECRET, ttl_min=-1)
    with pytest.raises(InvalidToken):
        decode_token(token, secret=SECRET)
