import pytest
from fastapi import HTTPException

from garda_ai_backend.api.ingest_auth import _verify_ingest


def test_verify_ingest_accepts_matching():
    _verify_ingest("Bearer s3cret", "s3cret")


@pytest.mark.parametrize("header", [None, "s3cret", "Bearer wrong", "Basic s3cret"])
def test_verify_ingest_rejects(header):
    with pytest.raises(HTTPException) as exc:
        _verify_ingest(header, "s3cret")
    assert exc.value.status_code == 401
