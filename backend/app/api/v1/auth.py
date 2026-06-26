import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Request, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.database import get_db
from app.config import settings
from app.core.security import (
    hash_password, verify_password, create_access_token,
    create_refresh_token, hash_token, generate_password_reset_token,
    generate_invitation_token,
)
from app.core.dependencies import get_current_user, get_client_ip
from app.core.exceptions import (
    UnauthorizedError, ConflictError, NotFoundError, AccountLockedError, ValidationError
)
from app.models.user import User, RefreshToken, PasswordResetToken
from app.models.organization import Organization, OrganizationMembership, Invitation, SubscriptionPlan, AuditLog
from app.schemas.auth import (
    LoginRequest, LoginResponse, RegisterRequest, RegisterResponse,
    RefreshTokenRequest, ForgotPasswordRequest, ResetPasswordRequest,
    ChangePasswordRequest, InviteAcceptRequest,
)

router = APIRouter()


async def _create_audit_log(db: AsyncSession, action: str, user_id=None, org_id=None, details=None, ip=None, success=True):
    log = AuditLog(
        organization_id=org_id,
        user_id=user_id,
        action=action,
        details=details or {},
        ip_address=ip,
        success=success,
    )
    db.add(log)


@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(
    data: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    # Check email uniqueness
    existing = await db.execute(select(User).where(User.email == data.email.lower()))
    if existing.scalar_one_or_none():
        raise ConflictError("Email already registered")

    # Create user
    user = User(
        email=data.email.lower(),
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        is_verified=True,  # Auto-verify for now; add email verification in production
    )
    db.add(user)
    await db.flush()

    # Get or create free plan
    plan_result = await db.execute(select(SubscriptionPlan).where(SubscriptionPlan.name == "free"))
    plan = plan_result.scalar_one_or_none()
    if not plan:
        plan = SubscriptionPlan(
            name="free",
            display_name="Free Tier",
            max_servers=5,
            max_users=3,
            max_proxmox_connections=1,
            ai_analysis_enabled=False,
        )
        db.add(plan)
        await db.flush()

    # Create organization with slug
    import re
    slug_base = re.sub(r"[^a-z0-9-]", "-", data.organization_name.lower())[:40]
    slug = slug_base
    counter = 1
    while True:
        existing_org = await db.execute(select(Organization).where(Organization.slug == slug))
        if not existing_org.scalar_one_or_none():
            break
        slug = f"{slug_base}-{counter}"
        counter += 1

    org = Organization(
        name=data.organization_name,
        slug=slug,
        plan_id=plan.id,
        contact_email=data.email.lower(),
    )
    db.add(org)
    await db.flush()

    # Add user as owner
    membership = OrganizationMembership(
        organization_id=org.id,
        user_id=user.id,
        role="owner",
        accepted_at=datetime.now(timezone.utc),
    )
    db.add(membership)

    await _create_audit_log(db, "user.register", user_id=user.id, org_id=org.id, ip=get_client_ip(request))
    await db.commit()
    await db.refresh(user)

    # Create tokens
    access_token = create_access_token({"sub": str(user.id), "org_id": str(org.id), "role": "owner"})
    raw_refresh, refresh_hash = create_refresh_token()
    rt = RefreshToken(
        user_id=user.id,
        token_hash=refresh_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("User-Agent", ""),
    )
    db.add(rt)
    await db.commit()

    return RegisterResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        token_type="bearer",
        user_id=str(user.id),
        organization_id=str(org.id),
        organization_slug=org.slug,
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    data: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == data.email.lower()))
    user = result.scalar_one_or_none()

    ip = get_client_ip(request)

    if not user:
        await _create_audit_log(db, "auth.login_failed", details={"email": data.email, "reason": "user_not_found"}, ip=ip, success=False)
        await db.commit()
        raise UnauthorizedError("Invalid email or password")

    # Check account lock
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        raise AccountLockedError()

    if not verify_password(data.password, user.hashed_password):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.MAX_LOGIN_ATTEMPTS:
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCOUNT_LOCKOUT_MINUTES)
        await _create_audit_log(db, "auth.login_failed", user_id=user.id, details={"reason": "wrong_password"}, ip=ip, success=False)
        await db.commit()
        raise UnauthorizedError("Invalid email or password")

    if not user.is_active:
        raise UnauthorizedError("Account is inactive")

    # Reset failed attempts
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = datetime.now(timezone.utc)
    user.last_login_ip = ip

    # Get primary org membership
    membership_result = await db.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.is_active == True,
        ).order_by(OrganizationMembership.created_at)
    )
    memberships = membership_result.scalars().all()
    primary_org_id = str(memberships[0].organization_id) if memberships else None
    primary_role = memberships[0].role if memberships else None

    access_token = create_access_token({
        "sub": str(user.id),
        "org_id": primary_org_id,
        "role": primary_role or "viewer",
        "is_platform_admin": user.is_platform_admin,
    })
    raw_refresh, refresh_hash = create_refresh_token()
    rt = RefreshToken(
        user_id=user.id,
        token_hash=refresh_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
        ip_address=ip,
        user_agent=request.headers.get("User-Agent", ""),
    )
    db.add(rt)

    await _create_audit_log(db, "auth.login", user_id=user.id, org_id=uuid.UUID(primary_org_id) if primary_org_id else None, ip=ip)
    await db.commit()

    return LoginResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        token_type="bearer",
        user_id=str(user.id),
        full_name=user.full_name,
        email=user.email,
        is_platform_admin=user.is_platform_admin,
        organizations=[
            {"id": str(m.organization_id), "role": m.role}
            for m in memberships
        ],
    )


@router.post("/refresh", response_model=LoginResponse)
async def refresh_token(
    data: RefreshTokenRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    token_hash = hash_token(data.refresh_token)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked == False,
        )
    )
    rt = result.scalar_one_or_none()
    if not rt or rt.expires_at < datetime.now(timezone.utc):
        raise UnauthorizedError("Invalid or expired refresh token")

    # Revoke old token (rotation)
    rt.revoked = True

    user = await db.get(User, rt.user_id)
    if not user or not user.is_active:
        raise UnauthorizedError("User not found or inactive")

    membership_result = await db.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.is_active == True,
        ).order_by(OrganizationMembership.created_at)
    )
    memberships = membership_result.scalars().all()
    primary_org_id = str(memberships[0].organization_id) if memberships else None
    primary_role = memberships[0].role if memberships else None

    access_token = create_access_token({
        "sub": str(user.id),
        "org_id": primary_org_id,
        "role": primary_role or "viewer",
        "is_platform_admin": user.is_platform_admin,
    })
    raw_refresh, refresh_hash = create_refresh_token()
    new_rt = RefreshToken(
        user_id=user.id,
        token_hash=refresh_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("User-Agent", ""),
    )
    db.add(new_rt)
    await db.commit()

    return LoginResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        token_type="bearer",
        user_id=str(user.id),
        full_name=user.full_name,
        email=user.email,
        is_platform_admin=user.is_platform_admin,
        organizations=[{"id": str(m.organization_id), "role": m.role} for m in memberships],
    )


@router.post("/logout")
async def logout(
    data: RefreshTokenRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    token_hash = hash_token(data.refresh_token)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.user_id == current_user.id,
        )
    )
    rt = result.scalar_one_or_none()
    if rt:
        rt.revoked = True
        await db.commit()
    return {"message": "Logged out successfully"}


@router.post("/forgot-password")
async def forgot_password(
    data: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == data.email.lower()))
    user = result.scalar_one_or_none()
    # Always return success to prevent enumeration
    if user and user.is_active:
        raw_token, token_hash = generate_password_reset_token()
        prt = PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
        )
        db.add(prt)
        await db.commit()
        # TODO: Send email notification
    return {"message": "If your email is registered, you will receive a password reset link"}


@router.post("/reset-password")
async def reset_password(
    data: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    from app.core.security import hash_token as ht
    token_hash = ht(data.token)
    result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used == False,
        )
    )
    prt = result.scalar_one_or_none()
    if not prt or prt.expires_at < datetime.now(timezone.utc):
        raise ValidationError("Invalid or expired reset token")

    user = await db.get(User, prt.user_id)
    if not user:
        raise NotFoundError("User")

    user.hashed_password = hash_password(data.new_password)
    prt.used = True

    # Revoke all refresh tokens
    await db.execute(
        update(RefreshToken).where(RefreshToken.user_id == user.id).values(revoked=True)
    )
    await db.commit()
    return {"message": "Password reset successfully"}


@router.post("/accept-invite")
async def accept_invitation(
    data: InviteAcceptRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Invitation).where(
            Invitation.token == data.token,
            Invitation.is_accepted == False,
        )
    )
    invite = result.scalar_one_or_none()
    if not invite or invite.expires_at < datetime.now(timezone.utc):
        raise ValidationError("Invalid or expired invitation")

    # Check if user exists
    user_result = await db.execute(select(User).where(User.email == invite.email))
    user = user_result.scalar_one_or_none()

    if not user:
        if not data.password or not data.full_name:
            raise ValidationError("Password and full name are required for new users")
        user = User(
            email=invite.email,
            hashed_password=hash_password(data.password),
            full_name=data.full_name,
            is_verified=True,
        )
        db.add(user)
        await db.flush()

    # Create membership
    existing_membership = await db.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == invite.organization_id,
            OrganizationMembership.user_id == user.id,
        )
    )
    if not existing_membership.scalar_one_or_none():
        membership = OrganizationMembership(
            organization_id=invite.organization_id,
            user_id=user.id,
            role=invite.role,
            invited_by_id=invite.invited_by_id,
            invited_at=invite.created_at,
            accepted_at=datetime.now(timezone.utc),
        )
        db.add(membership)

    invite.is_accepted = True
    await db.commit()
    return {"message": "Invitation accepted", "email": invite.email}
