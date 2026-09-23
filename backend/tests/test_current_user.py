"""get_current_user bağımlılığı testleri: sahte DB oturumuyla."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.core.security import create_access_token, create_refresh_token
from app.middleware.auth import get_current_user


def bearer(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def make_db(user):
    db = MagicMock()
    db.get = AsyncMock(return_value=user)
    return db


def make_user(**overrides):
    fields = dict(
        id="user-1",
        org_id="org-1",
        email="ali@example.com",
        role="admin",
        is_active=True,
        deleted_at=None,
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


async def test_valid_token_returns_user_with_db_role_and_org():
    # Token'daki rol/organizasyon eski olsa bile DB'deki güncel değerler kullanılır
    token = create_access_token("user-1", org_id="eski-org", role="user")

    current = await get_current_user(bearer(token), make_db(make_user()))

    assert (current.id, current.org_id, current.role) == ("user-1", "org-1", "admin")


async def test_missing_credentials_is_401():
    with pytest.raises(HTTPException) as exc:
        await get_current_user(None, make_db(make_user()))

    assert exc.value.status_code == 401
    assert exc.value.headers == {"WWW-Authenticate": "Bearer"}


async def test_garbage_token_is_401():
    with pytest.raises(HTTPException) as exc:
        await get_current_user(bearer("abc.def.ghi"), make_db(make_user()))

    assert exc.value.status_code == 401


async def test_refresh_token_cannot_be_used_as_access_token():
    token = create_refresh_token("user-1")

    with pytest.raises(HTTPException) as exc:
        await get_current_user(bearer(token), make_db(make_user()))

    assert exc.value.status_code == 401


@pytest.mark.parametrize(
    "user",
    [
        None,
        make_user(is_active=False),
        make_user(deleted_at=datetime.now(timezone.utc)),
    ],
    ids=["missing", "inactive", "deleted"],
)
async def test_unusable_user_is_401(user):
    token = create_access_token("user-1", org_id="org-1", role="admin")

    with pytest.raises(HTTPException) as exc:
        await get_current_user(bearer(token), make_db(user))

    assert exc.value.status_code == 401
