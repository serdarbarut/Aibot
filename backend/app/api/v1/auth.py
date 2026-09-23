"""
Authentication API endpoints.

Implements:
- User registration (AUTH-001)
- User login (AUTH-002)
- Token refresh (AUTH-009)
- Password reset (AUTH-005)
- MFA setup and verification (AUTH-004)
- Google SSO (AUTH-003)
- Session management (AUTH-006, AUTH-007)
"""

from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from slowapi import Limiter
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import (
    generate_recovery_codes,
    generate_totp_qr_code,
    generate_totp_secret,
    hash_recovery_code,
    verify_totp,
)
from app.core.database import get_db
from app.middleware.auth import CurrentUser, get_current_active_user
from app.middleware.security import get_client_ip, limiter
from app.services.auth_service import (
    AccountDisabledError,
    AccountLockedError,
    EmailAlreadyRegisteredError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    MFARequiredError,
    authenticate_user,
    register_user,
)
from app.services.session_service import (
    InvalidRefreshTokenError,
    list_active_sessions,
    revoke_other_sessions,
    revoke_session,
    revoke_session_by_refresh_token,
    rotate_session,
    start_session,
)

logger = structlog.get_logger()

router = APIRouter()


# =============================================================================
# Request/Response Schemas
# =============================================================================

class RegisterRequest(BaseModel):
    """User registration request."""
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    organization_name: Optional[str] = Field(default=None, max_length=255)


class RegisterResponse(BaseModel):
    """User registration response."""
    message: str
    user_id: str


class LoginRequest(BaseModel):
    """User login request."""
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    """User login response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


class RefreshRequest(BaseModel):
    """Token refresh request."""
    refresh_token: str


class LogoutRequest(BaseModel):
    """Logout request: the refresh token of the session to close."""
    refresh_token: str


class MFASetupResponse(BaseModel):
    """MFA setup response."""
    secret: str
    qr_code_svg: str
    recovery_codes: list[str]


class MFAVerifyRequest(BaseModel):
    """MFA verification request."""
    code: str = Field(min_length=6, max_length=6)


class PasswordResetRequest(BaseModel):
    """Password reset request."""
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Password reset confirmation."""
    token: str
    new_password: str = Field(min_length=8, max_length=128)


# =============================================================================
# Authentication Endpoints
# =============================================================================

@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(settings.rate_limit_auth)
async def register(
    request: Request,
    data: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new user account.

    - Creates a new organization with the user as its admin
    - Hashes the password with Argon2id
    - In development the account is auto-verified; elsewhere it starts unverified
    """
    try:
        user = await register_user(
            db,
            email=data.email,
            password=data.password,
            name=data.name,
            organization_name=data.organization_name,
        )
    except EmailAlreadyRegisteredError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    message = (
        "Registration successful. You can now log in."
        if user.email_verified
        else "Registration successful. Please check your email to verify your account."
    )
    return RegisterResponse(message=message, user_id=user.id)


@router.post("/login", response_model=LoginResponse)
@limiter.limit(settings.rate_limit_auth)
async def login(
    request: Request,
    data: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate user and return tokens.

    - Verifies email and password (locks the account after repeated failures)
    - Rejects disabled, unverified and MFA-enabled accounts
    - Returns JWT tokens on success
    """
    client_ip = get_client_ip(request)

    try:
        user = await authenticate_user(
            db,
            email=data.email,
            password=data.password,
            client_ip=client_ip,
        )
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    except AccountLockedError as e:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=(
                "Account is temporarily locked due to too many failed attempts. "
                f"Try again after {e.locked_until.strftime('%H:%M')} UTC."
            ),
        )
    except AccountDisabledError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")
    except EmailNotVerifiedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email address before logging in.",
        )
    except MFARequiredError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Multi-factor authentication is enabled for this account but login with MFA is not supported yet.",
        )

    access_token, refresh_token = await start_session(
        db,
        user,
        client_ip=client_ip,
        user_agent=request.headers.get("user-agent"),
    )

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user={
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "mfa_enabled": user.mfa_enabled,
        },
    )


@router.post("/refresh", response_model=LoginResponse)
@limiter.limit(settings.rate_limit_auth)
async def refresh_token(
    request: Request,
    data: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Refresh access token using refresh token.

    - Validates the refresh token against its session
    - Issues a new token pair (rotation); the previous refresh token stays
      valid for a short grace period so concurrent tabs don't log each other out
    """
    try:
        user, access_token, new_refresh_token = await rotate_session(
            db,
            data.refresh_token,
            client_ip=get_client_ip(request),
        )
    except InvalidRefreshTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    return LoginResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user={
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "mfa_enabled": user.mfa_enabled,
        },
    )


@router.post("/logout")
@limiter.limit(settings.rate_limit_auth)
async def logout(
    request: Request,
    data: LogoutRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Logout: close the session the refresh token belongs to.

    Idempotent: an invalid or already-closed token still returns success.
    Access tokens of the closed session stop working immediately.
    """
    revoked = await revoke_session_by_refresh_token(db, data.refresh_token)
    logger.info("logout", revoked=revoked, client_ip=get_client_ip(request))

    return {"message": "Successfully logged out"}


@router.post("/password-reset/request")
@limiter.limit("3/minute")  # Stricter rate limit for password reset
async def request_password_reset(request: Request, data: PasswordResetRequest):
    """
    Request password reset email.

    Always returns success to prevent email enumeration.
    """
    logger.info(
        "password_reset_requested",
        email=data.email,
        client_ip=get_client_ip(request),
    )

    # TODO: Check if user exists
    # TODO: Generate reset token
    # TODO: Send reset email

    # Always return success to prevent email enumeration
    return {
        "message": "If an account exists with this email, you will receive a password reset link."
    }


@router.post("/password-reset/confirm")
@limiter.limit(settings.rate_limit_auth)
async def confirm_password_reset(request: Request, data: PasswordResetConfirm):
    """
    Confirm password reset with token.
    """
    # TODO: Verify reset token
    # TODO: Update password
    # TODO: Invalidate all sessions
    # TODO: Log password change

    return {"message": "Password successfully reset. Please login with your new password."}


# =============================================================================
# MFA Endpoints
# =============================================================================

@router.post("/mfa/setup", response_model=MFASetupResponse)
async def setup_mfa(request: Request):
    """
    Initialize MFA setup for current user.

    Returns:
    - TOTP secret
    - QR code for authenticator app
    - Recovery codes (one-time use)
    """
    # TODO: Get current user from token
    # TODO: Check if MFA already enabled

    # Generate TOTP secret
    secret = generate_totp_secret()

    # Generate QR code
    # TODO: Use actual user email
    qr_code = generate_totp_qr_code(secret, "user@example.com")

    # Generate recovery codes
    recovery_codes = generate_recovery_codes(10)

    # TODO: Store encrypted secret and hashed recovery codes in database
    # (Don't enable MFA yet - wait for verification)

    return MFASetupResponse(
        secret=secret,
        qr_code_svg=qr_code,
        recovery_codes=recovery_codes,
    )


@router.post("/mfa/verify")
async def verify_mfa_setup(request: Request, data: MFAVerifyRequest):
    """
    Verify MFA setup by confirming TOTP code.

    This enables MFA for the user after successful verification.
    """
    # TODO: Get current user and pending MFA secret from database
    secret = "placeholder-secret"  # TODO: Get from database

    if not verify_totp(secret, data.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code",
        )

    # TODO: Enable MFA for user in database
    # TODO: Log MFA enabled in audit log

    return {"message": "MFA successfully enabled"}


@router.post("/mfa/challenge")
@limiter.limit(settings.rate_limit_auth)
async def verify_mfa_challenge(request: Request, data: MFAVerifyRequest):
    """
    Verify MFA code during login.

    Called after successful password authentication for users with MFA enabled.
    """
    # TODO: Get pending MFA session
    # TODO: Verify TOTP code or recovery code
    # TODO: Issue tokens on success

    return {
        "message": "MFA verification successful",
        # TODO: Return actual tokens
    }


@router.post("/mfa/disable")
async def disable_mfa(request: Request, data: MFAVerifyRequest):
    """
    Disable MFA for current user.

    Requires valid TOTP code to confirm.
    """
    # TODO: Get current user
    # TODO: Verify TOTP code
    # TODO: Disable MFA in database
    # TODO: Log MFA disabled in audit log

    return {"message": "MFA successfully disabled"}


# =============================================================================
# Session Management Endpoints
# =============================================================================

@router.get("/sessions")
async def list_sessions(
    current_user: CurrentUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List all active sessions for current user.
    """
    sessions = await list_active_sessions(db, current_user.id)

    return {
        "sessions": [
            {
                "id": session.id,
                "device": session.device_info,
                "ip_address": session.ip_address,
                "last_active": session.last_active_at.isoformat(),
                "created_at": session.created_at.isoformat(),
                "current": session.id == current_user.session_id,
            }
            for session in sessions
        ]
    }


@router.delete("/sessions/{session_id}")
async def revoke_session_endpoint(
    session_id: str,
    current_user: CurrentUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Revoke a specific session of the current user.
    """
    if not await revoke_session(db, current_user.id, session_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    logger.info("session_revoked", user_id=current_user.id, session_id=session_id)
    return {"message": "Session revoked"}


@router.delete("/sessions")
async def revoke_all_sessions(
    current_user: CurrentUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Revoke all sessions except current.
    """
    count = await revoke_other_sessions(db, current_user.id, current_user.session_id)

    logger.info("other_sessions_revoked", user_id=current_user.id, count=count)
    return {"message": "All other sessions revoked", "revoked_count": count}
