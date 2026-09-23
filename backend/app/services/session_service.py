"""
Oturum yönetimi: oturum açma, refresh token rotasyonu, çıkış ve oturum listesi.

Her giriş bir `sessions` satırı oluşturur. Refresh token yenilenince aynı satır
güncellenir (oturum kimliği sabit kalır); bir önceki token `REFRESH_GRACE_SECONDS`
boyunca daha geçerli sayılır. Aynı anda yenileme yapan iki sekme bu sayede
birbirini oturumdan atmaz.
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import create_token_pair, verify_token
from app.models.user import Session, User

logger = structlog.get_logger()

# Yenilemeden sonra bir önceki refresh token'ın hâlâ kabul edildiği süre
REFRESH_GRACE_SECONDS = 30


class InvalidRefreshTokenError(Exception):
    """Refresh token geçersiz, süresi dolmuş, iptal edilmiş veya oturumu kapanmış."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _session_expiry(now: datetime) -> datetime:
    return now + timedelta(days=settings.jwt_refresh_token_expire_days)


def is_session_usable(session: Optional[Session], user_id: str, now: Optional[datetime] = None) -> bool:
    """Oturum bu kullanıcıya ait, aktif, iptal edilmemiş ve süresi dolmamış mı?"""
    now = now or _now()
    return (
        session is not None
        and session.user_id == user_id
        and session.is_active
        and session.revoked_at is None
        and session.expires_at > now
    )


async def start_session(
    db: AsyncSession,
    user: User,
    *,
    client_ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> tuple[str, str]:
    """Yeni oturum açar ve (access_token, refresh_token) döndürür."""
    now = _now()
    session_id = str(uuid4())
    jti = secrets.token_urlsafe(16)

    access_token, refresh_token = create_token_pair(
        user_id=user.id,
        org_id=user.org_id,
        role=user.role,
        session_id=session_id,
        jti=jti,
    )

    db.add(
        Session(
            id=session_id,
            user_id=user.id,
            refresh_token_jti=jti,
            device_info=user_agent[:255] if user_agent else None,
            ip_address=client_ip,
            user_agent=user_agent,
            last_active_at=now,
            expires_at=_session_expiry(now),
        )
    )
    await db.flush()
    return access_token, refresh_token


async def rotate_session(
    db: AsyncSession,
    refresh_token: str,
    *,
    client_ip: Optional[str] = None,
) -> tuple[User, str, str]:
    """
    Refresh token'ı doğrular ve yeni bir token çifti verir.

    Token ya oturumun güncel token'ıdır ya da son yenilemeden beri
    REFRESH_GRACE_SECONDS geçmemiş bir önceki token'dır. Başka her durumda
    InvalidRefreshTokenError fırlatır.
    """
    token_data = verify_token(refresh_token, token_type="refresh")
    if token_data is None or not token_data.jti:
        raise InvalidRefreshTokenError()

    # Satırı kilitle: aynı anda gelen iki yenileme sırayla işlensin
    result = await db.execute(
        select(Session)
        .where(
            or_(
                Session.refresh_token_jti == token_data.jti,
                Session.previous_refresh_token_jti == token_data.jti,
            )
        )
        .with_for_update()
    )
    session = result.scalars().first()

    now = _now()
    if not is_session_usable(session, token_data.user_id, now):
        raise InvalidRefreshTokenError()

    if session.refresh_token_jti != token_data.jti:
        # Bir önceki token: yalnızca tolerans süresi içinde kabul edilir
        if session.rotated_at is None or now - session.rotated_at > timedelta(seconds=REFRESH_GRACE_SECONDS):
            raise InvalidRefreshTokenError()

    user = await db.get(User, session.user_id)
    if user is None or user.deleted_at is not None or not user.is_active:
        raise InvalidRefreshTokenError()

    new_jti = secrets.token_urlsafe(16)
    access_token, new_refresh_token = create_token_pair(
        user_id=user.id,
        org_id=user.org_id,
        role=user.role,
        session_id=session.id,
        jti=new_jti,
    )

    session.previous_refresh_token_jti = session.refresh_token_jti
    session.refresh_token_jti = new_jti
    session.rotated_at = now
    session.last_active_at = now
    session.expires_at = _session_expiry(now)
    if client_ip:
        session.ip_address = client_ip

    await db.flush()
    return user, access_token, new_refresh_token


def _revoke(session: Session, now: datetime) -> None:
    session.is_active = False
    session.revoked_at = now


async def revoke_session_by_refresh_token(db: AsyncSession, refresh_token: str) -> bool:
    """
    Çıkış: refresh token'ın oturumunu kapatır.

    Geçersiz veya süresi dolmuş token sessizce yok sayılır (çıkış idempotenttir).
    Döndürülen değer bir oturumun kapatılıp kapatılmadığıdır.
    """
    token_data = verify_token(refresh_token, token_type="refresh")
    if token_data is None or not token_data.jti:
        return False

    result = await db.execute(
        select(Session).where(
            or_(
                Session.refresh_token_jti == token_data.jti,
                Session.previous_refresh_token_jti == token_data.jti,
            ),
            Session.user_id == token_data.user_id,
        )
    )
    session = result.scalars().first()
    if session is None or session.revoked_at is not None:
        return False

    _revoke(session, _now())
    await db.flush()
    return True


async def list_active_sessions(db: AsyncSession, user_id: str) -> list[Session]:
    """Kullanıcının aktif oturumları, en son kullanılan başta."""
    result = await db.execute(
        select(Session)
        .where(
            Session.user_id == user_id,
            Session.is_active.is_(True),
            Session.revoked_at.is_(None),
            Session.expires_at > _now(),
        )
        .order_by(Session.last_active_at.desc())
    )
    return list(result.scalars().all())


async def revoke_session(db: AsyncSession, user_id: str, session_id: str) -> bool:
    """Kullanıcının kendi oturumunu kapatır; oturum yoksa veya başkasınınsa False."""
    session = await db.get(Session, session_id)
    if session is None or session.user_id != user_id or session.revoked_at is not None:
        return False

    _revoke(session, _now())
    await db.flush()
    return True


async def revoke_other_sessions(db: AsyncSession, user_id: str, keep_session_id: Optional[str]) -> int:
    """Mevcut oturum dışındaki tüm aktif oturumları kapatır; kapatılan sayısını döndürür."""
    now = _now()
    count = 0
    for session in await list_active_sessions(db, user_id):
        if session.id != keep_session_id:
            _revoke(session, now)
            count += 1
    await db.flush()
    return count
