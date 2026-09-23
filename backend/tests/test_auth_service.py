"""auth_service testleri: sahte DB oturumuyla, veritabanı olmadan."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.security import hash_password
from app.models.user import Organization, User
from app.services import auth_service as svc

PASSWORD = "Sifre-12345"
PASSWORD_HASH = hash_password(PASSWORD)


def make_db(user=None):
    """db.execute(...).scalars().first() -> user döndüren sahte oturum."""
    result = MagicMock()
    result.scalars.return_value.first.return_value = user
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


def make_user(**overrides):
    fields = dict(
        id="user-1",
        org_id="org-1",
        email="ali@example.com",
        password_hash=PASSWORD_HASH,
        is_active=True,
        email_verified=True,
        mfa_enabled=False,
        failed_login_attempts=0,
        locked_until=None,
        last_login_at=None,
        last_login_ip=None,
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


# --- yardımcılar -------------------------------------------------------------

def test_normalize_email_lowercases_and_strips():
    assert svc.normalize_email("  Ali@Example.COM ") == "ali@example.com"


@pytest.mark.parametrize(
    "value, expected",
    [
        ("Şirket Ltd", "sirket-ltd"),
        ("Işık Çağrı Öğüt", "isik-cagri-ogut"),
        ("  A & B / C!! ", "a-b-c"),
        ("!!!", "org"),
        ("", "org"),
    ],
)
def test_slugify(value, expected):
    assert svc.slugify(value) == expected


def test_slugify_is_truncated():
    assert len(svc.slugify("a" * 500)) == 80


# --- register_user -----------------------------------------------------------

async def test_register_creates_admin_user_and_organization():
    db = make_db(user=None)

    user = await svc.register_user(
        db,
        email="Ali@Example.com",
        password=PASSWORD,
        name=" Ali Veli ",
        organization_name="Şirket Ltd",
    )

    added = [call.args[0] for call in db.add.call_args_list]
    org = next(o for o in added if isinstance(o, Organization))
    assert org.name == "Şirket Ltd"
    assert org.slug.startswith("sirket-ltd-")
    assert user.email == "ali@example.com"
    assert user.name == "Ali Veli"
    assert user.role == "admin"
    assert user.password_hash.startswith("$argon2id$")
    assert user.password_hash != PASSWORD


async def test_register_uses_user_name_when_no_organization_name():
    db = make_db(user=None)

    await svc.register_user(db, email="a@b.com", password=PASSWORD, name="Ali Veli")

    org = next(c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], Organization))
    assert org.name == "Ali Veli"


async def test_register_rejects_existing_email():
    db = make_db(user=make_user())

    with pytest.raises(svc.EmailAlreadyRegisteredError):
        await svc.register_user(db, email="ali@example.com", password=PASSWORD, name="Ali")

    db.add.assert_not_called()


@pytest.mark.parametrize("is_development, expected_verified", [(True, True), (False, False)])
async def test_register_email_verification_depends_on_environment(
    monkeypatch, is_development, expected_verified
):
    monkeypatch.setattr(svc, "settings", SimpleNamespace(is_development=is_development))

    user = await svc.register_user(make_db(user=None), email="a@b.com", password=PASSWORD, name="Ali")

    assert user.email_verified is expected_verified


# --- authenticate_user -------------------------------------------------------

async def test_login_success_resets_counters_and_records_activity():
    user = make_user(failed_login_attempts=3)

    result = await svc.authenticate_user(
        make_db(user), email="ALI@example.com", password=PASSWORD, client_ip="10.0.0.1"
    )

    assert result is user
    assert user.failed_login_attempts == 0
    assert user.locked_until is None
    assert user.last_login_ip == "10.0.0.1"
    assert user.last_login_at is not None


async def test_login_unknown_email_is_invalid_credentials():
    with pytest.raises(svc.InvalidCredentialsError):
        await svc.authenticate_user(make_db(None), email="yok@example.com", password=PASSWORD)


async def test_login_user_without_password_is_invalid_credentials():
    with pytest.raises(svc.InvalidCredentialsError):
        await svc.authenticate_user(
            make_db(make_user(password_hash=None)), email="ali@example.com", password=PASSWORD
        )


async def test_wrong_password_increments_counter_and_commits():
    user = make_user()
    db = make_db(user)

    with pytest.raises(svc.InvalidCredentialsError):
        await svc.authenticate_user(db, email="ali@example.com", password="yanlis")

    assert user.failed_login_attempts == 1
    assert user.locked_until is None
    # get_db hata sonrası rollback yapar; sayaç önceden commit edilmeli
    db.commit.assert_awaited_once()


async def test_account_locks_after_max_failed_attempts():
    user = make_user(failed_login_attempts=svc.MAX_FAILED_LOGIN_ATTEMPTS - 1)

    with pytest.raises(svc.InvalidCredentialsError):
        await svc.authenticate_user(make_db(user), email="ali@example.com", password="yanlis")

    assert user.failed_login_attempts == 0
    remaining = user.locked_until - datetime.now(timezone.utc)
    assert timedelta(minutes=svc.LOCKOUT_MINUTES - 1) < remaining <= timedelta(minutes=svc.LOCKOUT_MINUTES)


async def test_locked_account_is_rejected_even_with_correct_password():
    locked_until = datetime.now(timezone.utc) + timedelta(minutes=5)
    user = make_user(locked_until=locked_until)

    with pytest.raises(svc.AccountLockedError) as exc:
        await svc.authenticate_user(make_db(user), email="ali@example.com", password=PASSWORD)

    assert exc.value.locked_until == locked_until


async def test_expired_lock_allows_login_and_is_cleared():
    user = make_user(locked_until=datetime.now(timezone.utc) - timedelta(minutes=1))

    await svc.authenticate_user(make_db(user), email="ali@example.com", password=PASSWORD)

    assert user.locked_until is None


@pytest.mark.parametrize(
    "overrides, error",
    [
        ({"is_active": False}, svc.AccountDisabledError),
        ({"email_verified": False}, svc.EmailNotVerifiedError),
        ({"mfa_enabled": True}, svc.MFARequiredError),
    ],
)
async def test_account_state_is_checked_after_password(overrides, error):
    user = make_user(**overrides)

    with pytest.raises(error):
        await svc.authenticate_user(make_db(user), email="ali@example.com", password=PASSWORD)


async def test_disabled_account_with_wrong_password_does_not_leak_state():
    user = make_user(is_active=False)

    with pytest.raises(svc.InvalidCredentialsError):
        await svc.authenticate_user(make_db(user), email="ali@example.com", password="yanlis")
