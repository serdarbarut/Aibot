"""
Kimlik doğrulama iş mantığı: kayıt ve giriş.

Endpoint'ler (api/v1/auth.py) bu modülü çağırır; veritabanı işleri burada
toplanır ki HTTP katmanından bağımsız test edilebilsin.
"""

import asyncio
import re
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Optional

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import check_needs_rehash, hash_password, verify_password
from app.models.user import Organization, User

logger = structlog.get_logger()

# Art arda başarısız girişte hesap geçici kilitlenir
MAX_FAILED_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


class AuthError(Exception):
    """Kimlik doğrulama hatalarının ortak tabanı."""


class EmailAlreadyRegisteredError(AuthError):
    """Bu e-posta ile zaten bir hesap var."""


class InvalidCredentialsError(AuthError):
    """E-posta veya parola hatalı."""


class AccountLockedError(AuthError):
    """Çok fazla başarısız deneme nedeniyle hesap geçici kilitli."""

    def __init__(self, locked_until: datetime):
        super().__init__("Account is temporarily locked")
        self.locked_until = locked_until


class AccountDisabledError(AuthError):
    """Hesap devre dışı bırakılmış."""


class EmailNotVerifiedError(AuthError):
    """E-posta adresi henüz doğrulanmamış."""


class MFARequiredError(AuthError):
    """Hesapta MFA açık; MFA ile giriş akışı henüz yazılmadı."""


def normalize_email(email: str) -> str:
    """E-postayı karşılaştırma için küçük harfe çevirir."""
    return email.strip().lower()


def slugify(value: str) -> str:
    """Metni URL uyumlu, ASCII bir slug'a çevirir (ör. 'Şirket Adı' -> 'sirket-adi')."""
    value = value.replace("ı", "i").replace("İ", "I")
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value[:80] or "org"


@lru_cache(maxsize=1)
def _dummy_password_hash() -> str:
    """Var olmayan hesaplar için sahte özet; yanıt süresi farkından hesap sızmasın diye."""
    return hash_password("dummy-password-for-timing-equalization")


async def _find_active_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    result = await db.execute(
        select(User).where(
            func.lower(User.email) == email,
            User.deleted_at.is_(None),
        )
    )
    return result.scalars().first()


async def register_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    name: str,
    organization_name: Optional[str] = None,
) -> User:
    """
    Yeni bir organizasyon ve onun ilk (admin) kullanıcısını oluşturur.

    Geliştirme ortamında e-posta doğrulaması atlanır (hesap doğrulanmış sayılır);
    diğer ortamlarda hesap doğrulanmamış başlar.
    """
    email = normalize_email(email)

    # Aynı e-postayla eşzamanlı iki kayıt birbirini görmeden geçmesin
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"register:{email}"})

    if await _find_active_user_by_email(db, email):
        raise EmailAlreadyRegisteredError()

    org_name = (organization_name or name).strip()
    organization = Organization(
        name=org_name,
        slug=f"{slugify(org_name)}-{secrets.token_hex(3)}",
    )
    db.add(organization)
    await db.flush()

    password_hash = await asyncio.to_thread(hash_password, password)
    user = User(
        org_id=organization.id,
        email=email,
        name=name.strip(),
        password_hash=password_hash,
        role="admin",
        email_verified=settings.is_development,
        is_active=True,
    )
    db.add(user)
    await db.flush()

    logger.info("user_registered", user_id=user.id, org_id=organization.id)
    return user


async def authenticate_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    client_ip: Optional[str] = None,
) -> User:
    """
    E-posta ve parolayı doğrular; başarılıysa kullanıcıyı döndürür.

    Başarısız denemeleri sayar ve limit aşılınca hesabı geçici kilitler.
    """
    email = normalize_email(email)
    user = await _find_active_user_by_email(db, email)

    if user is None or not user.password_hash:
        await asyncio.to_thread(verify_password, password, _dummy_password_hash())
        raise InvalidCredentialsError()

    now = datetime.now(timezone.utc)
    if user.locked_until and user.locked_until > now:
        raise AccountLockedError(user.locked_until)

    if not await asyncio.to_thread(verify_password, password, user.password_hash):
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts >= MAX_FAILED_LOGIN_ATTEMPTS:
            user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
            user.failed_login_attempts = 0
            logger.warning("account_locked", user_id=user.id, client_ip=client_ip)
        # İstek hata ile biteceği için get_db rollback yapar; sayaç kaybolmasın
        await db.commit()
        raise InvalidCredentialsError()

    # Parola doğru; hesap durumuna ancak bundan sonra bakılır (hesap varlığı sızmasın)
    if not user.is_active:
        raise AccountDisabledError()
    if not user.email_verified:
        raise EmailNotVerifiedError()
    if user.mfa_enabled:
        raise MFARequiredError()

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    user.last_login_ip = client_ip
    if check_needs_rehash(user.password_hash):
        user.password_hash = await asyncio.to_thread(hash_password, password)

    await db.flush()
    logger.info("login_success", user_id=user.id, client_ip=client_ip)
    return user
