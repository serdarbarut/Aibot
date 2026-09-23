"""get_current_user bağımlılığı testleri: sahte DB oturumuyla."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.core.security import create_access_token, create_refresh_token
from app.middleware.auth import get_current_user
from app.models.user import Session, User


def bearer(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


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


def make_session(**overrides):
    fields = dict(
        id="sess-1",
        user_id="user-1",
        is_active=True,
        revoked_at=None,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


def make_db(user, session):
    """db.get(User, ...) -> user, db.get(Session, ...) -> session"""
    async def get(model, _id):
        return {User: user, Session: session}[model]

    db = MagicMock()
    db.get = AsyncMock(side_effect=get)
    return db


def access_token(**kwargs):
    kwargs.setdefault("session_id", "sess-1")
    return create_access_token("user-1", org_id="org-1", role="admin", **kwargs)


async def test_valid_token_returns_user_with_db_role_and_org():
    # Token'daki rol/organizasyon eski olsa bile DB'deki güncel değerler kullanılır
    token = create_access_token("user-1", org_id="eski-org", role="user", session_id="sess-1")

    current = await get_current_user(bearer(token), make_db(make_user(), make_session()))

    assert (current.id, current.org_id, current.role) == ("user-1", "org-1", "admin")
    assert current.session_id == "sess-1"


async def test_missing_credentials_is_401():
    with pytest.raises(HTTPException) as exc:
        await get_current_user(None, make_db(make_user(), make_session()))

    assert exc.value.status_code == 401
    assert exc.value.headers == {"WWW-Authenticate": "Bearer"}


async def test_garbage_token_is_401():
    with pytest.raises(HTTPException) as exc:
        await get_current_user(bearer("abc.def.ghi"), make_db(make_user(), make_session()))

    assert exc.value.status_code == 401


async def test_refresh_token_cannot_be_used_as_access_token():
    token = create_refresh_token("user-1")

    with pytest.raises(HTTPException) as exc:
        await get_current_user(bearer(token), make_db(make_user(), make_session()))

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
    with pytest.raises(HTTPException) as exc:
        await get_current_user(bearer(access_token()), make_db(user, make_session()))

    assert exc.value.status_code == 401


@pytest.mark.parametrize(
    "session",
    [
        None,
        make_session(is_active=False),
        make_session(revoked_at=datetime.now(timezone.utc)),
        make_session(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)),
        make_session(user_id="baska-kullanici"),
    ],
    ids=["missing", "inactive", "revoked", "expired", "other-users"],
)
async def test_unusable_session_is_401(session):
    """Oturum kapatılınca access token süresi dolmasa da geçersiz olur."""
    with pytest.raises(HTTPException) as exc:
        await get_current_user(bearer(access_token()), make_db(make_user(), session))

    assert exc.value.status_code == 401


async def test_token_without_session_id_is_401():
    token = create_access_token("user-1", org_id="org-1", role="admin")  # sid yok

    with pytest.raises(HTTPException) as exc:
        await get_current_user(bearer(token), make_db(make_user(), make_session()))

    assert exc.value.status_code == 401
