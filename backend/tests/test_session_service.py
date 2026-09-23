"""session_service testleri: sahte DB oturumuyla, veritabanı olmadan."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.security import create_access_token, create_refresh_token, verify_token
from app.models.user import Session
from app.services import session_service as svc

NOW = datetime.now(timezone.utc)


def make_user(**overrides):
    fields = dict(id="user-1", org_id="org-1", role="admin", is_active=True, deleted_at=None)
    fields.update(overrides)
    return SimpleNamespace(**fields)


def make_session(**overrides):
    fields = dict(
        id="sess-1",
        user_id="user-1",
        refresh_token_jti="J1",
        previous_refresh_token_jti=None,
        rotated_at=None,
        is_active=True,
        revoked_at=None,
        expires_at=NOW + timedelta(days=3),
        last_active_at=NOW - timedelta(hours=1),
        ip_address=None,
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


def make_db(session=None, user=None):
    result = MagicMock()
    result.scalars.return_value.first.return_value = session
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.get = AsyncMock(return_value=session if user is None else user)
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


def rotate_db(session, user=None):
    """rotate_session için: execute -> session, db.get(User, ...) -> user."""
    db = make_db(session)
    db.get = AsyncMock(return_value=user if user is not None else make_user())
    return db


# --- is_session_usable ------------------------------------------------------

@pytest.mark.parametrize(
    "overrides, usable",
    [
        ({}, True),
        ({"is_active": False}, False),
        ({"revoked_at": NOW}, False),
        ({"expires_at": NOW - timedelta(seconds=1)}, False),
        ({"user_id": "baska"}, False),
    ],
)
def test_is_session_usable(overrides, usable):
    assert svc.is_session_usable(make_session(**overrides), "user-1") is usable


def test_missing_session_is_not_usable():
    assert svc.is_session_usable(None, "user-1") is False


# --- start_session ----------------------------------------------------------

async def test_start_session_stores_matching_jti_and_session_id():
    db = make_db()

    access, refresh = await svc.start_session(
        db, make_user(), client_ip="10.0.0.1", user_agent="Chrome " + "x" * 400
    )

    session = db.add.call_args.args[0]
    assert isinstance(session, Session)
    assert verify_token(refresh, "refresh").jti == session.refresh_token_jti
    assert verify_token(access, "access").session_id == session.id
    assert session.ip_address == "10.0.0.1"
    assert len(session.device_info) == 255
    assert timedelta(days=6) < session.expires_at - NOW < timedelta(days=8)


# --- rotate_session ---------------------------------------------------------

async def test_rotate_with_current_token_issues_new_pair():
    session = make_session()
    token = create_refresh_token("user-1", jti="J1")

    user, access, refresh = await svc.rotate_session(rotate_db(session), token, client_ip="10.0.0.2")

    new_jti = verify_token(refresh, "refresh").jti
    assert new_jti != "J1"
    assert session.refresh_token_jti == new_jti
    assert session.previous_refresh_token_jti == "J1"
    assert session.rotated_at is not None
    assert session.ip_address == "10.0.0.2"
    assert verify_token(access, "access").session_id == "sess-1"
    assert user.id == "user-1"


async def test_previous_token_is_accepted_within_grace_period():
    """İkinci sekme, ilk sekmenin yenilemesinden hemen sonra eski token'la gelir."""
    session = make_session(
        refresh_token_jti="J2", previous_refresh_token_jti="J1",
        rotated_at=datetime.now(timezone.utc) - timedelta(seconds=svc.REFRESH_GRACE_SECONDS - 5),
    )

    _, _, refresh = await svc.rotate_session(rotate_db(session), create_refresh_token("user-1", jti="J1"))

    # İlk sekmenin token'ı (J2) da geçerli kalır: yeni previous = eski current
    assert session.previous_refresh_token_jti == "J2"
    assert session.refresh_token_jti == verify_token(refresh, "refresh").jti


@pytest.mark.parametrize(
    "rotated_at",
    [datetime.now(timezone.utc) - timedelta(seconds=svc.REFRESH_GRACE_SECONDS + 5), None],
    ids=["grace-expired", "never-rotated"],
)
async def test_previous_token_is_rejected_outside_grace_period(rotated_at):
    session = make_session(refresh_token_jti="J2", previous_refresh_token_jti="J1", rotated_at=rotated_at)

    with pytest.raises(svc.InvalidRefreshTokenError):
        await svc.rotate_session(rotate_db(session), create_refresh_token("user-1", jti="J1"))

    assert session.refresh_token_jti == "J2"  # değişmedi


@pytest.mark.parametrize(
    "session",
    [
        None,
        make_session(is_active=False),
        make_session(revoked_at=NOW),
        make_session(expires_at=NOW - timedelta(seconds=1)),
        make_session(user_id="baska-kullanici"),
    ],
    ids=["unknown", "inactive", "revoked", "expired", "other-users"],
)
async def test_rotate_rejects_unusable_session(session):
    with pytest.raises(svc.InvalidRefreshTokenError):
        await svc.rotate_session(rotate_db(session), create_refresh_token("user-1", jti="J1"))


@pytest.mark.parametrize(
    "user",
    [None, make_user(is_active=False), make_user(deleted_at=NOW)],
    ids=["missing", "inactive", "deleted"],
)
async def test_rotate_rejects_unusable_user(user):
    db = make_db(make_session())
    db.get = AsyncMock(return_value=user)

    with pytest.raises(svc.InvalidRefreshTokenError):
        await svc.rotate_session(db, create_refresh_token("user-1", jti="J1"))


@pytest.mark.parametrize(
    "token",
    ["abc.def.ghi", create_access_token("user-1", session_id="sess-1")],
    ids=["garbage", "access-token"],
)
async def test_rotate_rejects_non_refresh_tokens(token):
    with pytest.raises(svc.InvalidRefreshTokenError):
        await svc.rotate_session(rotate_db(make_session()), token)


# --- logout / iptal ---------------------------------------------------------

async def test_logout_revokes_the_session():
    session = make_session()

    assert await svc.revoke_session_by_refresh_token(make_db(session), create_refresh_token("user-1", jti="J1"))

    assert session.is_active is False
    assert session.revoked_at is not None


@pytest.mark.parametrize(
    "session, token",
    [
        (None, create_refresh_token("user-1", jti="J1")),
        (make_session(revoked_at=NOW), create_refresh_token("user-1", jti="J1")),
        (make_session(), "abc.def.ghi"),
    ],
    ids=["unknown", "already-revoked", "garbage"],
)
async def test_logout_is_idempotent(session, token):
    assert await svc.revoke_session_by_refresh_token(make_db(session), token) is False


async def test_revoke_own_session():
    session = make_session()

    assert await svc.revoke_session(make_db(session), "user-1", "sess-1") is True
    assert session.is_active is False and session.revoked_at is not None


@pytest.mark.parametrize(
    "session",
    [None, make_session(user_id="baska-kullanici"), make_session(revoked_at=NOW)],
    ids=["missing", "other-users", "already-revoked"],
)
async def test_revoke_session_refuses_foreign_or_missing(session):
    assert await svc.revoke_session(make_db(session), "user-1", "sess-1") is False
    if session is not None and session.user_id != "user-1":
        assert session.is_active is True  # başkasının oturumuna dokunulmadı


async def test_revoke_other_sessions_keeps_the_current_one(monkeypatch):
    sessions = [make_session(id="a"), make_session(id="b"), make_session(id="c")]
    monkeypatch.setattr(svc, "list_active_sessions", AsyncMock(return_value=sessions))

    count = await svc.revoke_other_sessions(make_db(), "user-1", keep_session_id="b")

    assert count == 2
    assert [s.is_active for s in sessions] == [False, True, False]
