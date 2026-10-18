import pytest
from fastapi import HTTPException

from grafin_ai_scoring.api.auth import _verify


def test_verify_accepts_matching():
    _verify("Bearer s3cret", "s3cret")  # no raise


@pytest.mark.parametrize("header", [None, "s3cret", "Bearer wrong", "Basic s3cret"])
def test_verify_rejects(header):
    with pytest.raises(HTTPException) as exc:
        _verify(header, "s3cret")
    assert exc.value.status_code == 401
