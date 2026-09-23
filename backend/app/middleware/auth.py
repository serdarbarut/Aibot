"""
Authentication middleware and dependencies.

Provides FastAPI dependencies for:
- Getting the current authenticated user
- Role-based access control
- Organization context
"""

from typing import Optional

import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import verify_token
from app.models.user import Session, User
from app.services.session_service import is_session_usable

logger = structlog.get_logger()

# Bearer token security scheme
security = HTTPBearer(auto_error=False)


class CurrentUser:
    """Current authenticated user context."""

    def __init__(
        self,
        id: str,
        email: str,
        org_id: str,
        role: str = "member",
        is_active: bool = True,
        session_id: Optional[str] = None,
    ):
        self.id = id
        self.email = email
        self.org_id = org_id
        self.role = role
        self.is_active = is_active
        self.session_id = session_id


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """
    Get the current authenticated user from the JWT access token.

    Rolü ve organizasyonu token'daki iddialardan değil veritabanından alır;
    böylece rol değişikliği veya hesabın kapatılması hemen etkili olur.
    Token'ın bağlı olduğu oturum kapatılmışsa (çıkış, iptal) token süresi dolmasa
    da geçersizdir.
    """
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise unauthorized

    token_data = verify_token(credentials.credentials, token_type="access")
    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await db.get(User, token_data.user_id)
    if user is None or user.deleted_at is not None or not user.is_active:
        raise unauthorized

    if not token_data.session_id:
        raise unauthorized
    session = await db.get(Session, token_data.session_id)
    if not is_session_usable(session, user.id):
        raise unauthorized

    return CurrentUser(
        id=user.id,
        email=user.email,
        org_id=user.org_id,
        role=user.role,
        is_active=user.is_active,
        session_id=session.id,
    )


async def get_current_active_user(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Ensure the current user is active."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )
    return current_user


async def require_admin(
    current_user: CurrentUser = Depends(get_current_active_user),
) -> CurrentUser:
    """Require admin role."""
    if current_user.role not in ("admin", "owner"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


async def require_owner(
    current_user: CurrentUser = Depends(get_current_active_user),
) -> CurrentUser:
    """Require owner role."""
    if current_user.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner access required",
        )
    return current_user
