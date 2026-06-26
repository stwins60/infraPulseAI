import uuid
from typing import Optional
from fastapi import Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.core.security import decode_access_token, role_has_permission
from app.core.exceptions import UnauthorizedError, ForbiddenError, NotFoundError
from app.models.user import User
from app.models.organization import Organization, OrganizationMembership

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials:
        raise UnauthorizedError()

    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise UnauthorizedError("Invalid or expired token")

    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedError("Invalid token payload")

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id), User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise UnauthorizedError("User not found or inactive")

    return user


async def get_current_active_user(user: User = Depends(get_current_user)) -> User:
    if not user.is_active:
        raise UnauthorizedError("Inactive user")
    return user


async def get_platform_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_platform_admin:
        raise ForbiddenError("Platform admin access required")
    return user


class OrgContext:
    """Dependency that validates organization membership and provides org + membership."""

    def __init__(self, required_role: str = "viewer"):
        self.required_role = required_role

    async def __call__(
        self,
        org_id: uuid.UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ):
        # Platform admins can access any org
        if current_user.is_platform_admin:
            org = await db.get(Organization, org_id)
            if not org:
                raise NotFoundError("Organization")
            return org, None, current_user

        # Regular users need membership
        result = await db.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == org_id,
                OrganizationMembership.user_id == current_user.id,
                OrganizationMembership.is_active == True,
            )
        )
        membership = result.scalar_one_or_none()
        if not membership:
            raise ForbiddenError("Not a member of this organization")

        if not role_has_permission(membership.role, self.required_role):
            raise ForbiddenError(f"Role '{self.required_role}' or higher required")

        org = await db.get(Organization, org_id)
        if not org or not org.is_active:
            raise NotFoundError("Organization")

        return org, membership, current_user


def require_org_role(role: str = "viewer"):
    return OrgContext(required_role=role)


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
