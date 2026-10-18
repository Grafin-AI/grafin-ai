import pytest
from fastapi import HTTPException

from garda_ai_backend.api.deps import CurrentUser, require_role


def _user(role: str) -> CurrentUser:
    return CurrentUser(id=1, role=role)


def test_require_role_allows_match():
    guard = require_role("analyst", "admin")
    assert guard(_user("analyst")) is not None
    assert guard(_user("admin")).role == "admin"


def test_require_role_blocks_others():
    guard = require_role("admin")
    with pytest.raises(HTTPException) as exc:
        guard(_user("analyst"))
    assert exc.value.status_code == 403
