import pytest
from fastapi import HTTPException

from garda_ai_scoring.api.auth import require_token


def test_require_token_accepts_matching():
    require_token(authorization="Bearer s3cret", expected="s3cret")  # no raise


@pytest.mark.parametrize("header", [None, "s3cret", "Bearer wrong", "Basic s3cret"])
def test_require_token_rejects(header):
    with pytest.raises(HTTPException) as exc:
        require_token(authorization=header, expected="s3cret")
    assert exc.value.status_code == 401
