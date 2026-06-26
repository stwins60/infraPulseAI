from datetime import datetime, timedelta, timezone
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.core.dependencies import get_current_user, require_org_role
from app.core.exceptions import NotFoundError, ConflictError, ForbiddenError
from app.core.security import generate_invitation_token
from app.models.organization import Organization, OrganizationMembership, Invitation, SubscriptionPlan, AuditLog
from app.models.user import User
from app.models.server import Server
from app.models.proxmox import ProxmoxConnection
from app.schemas.organization import (
    OrganizationOut, OrganizationUpdate, InviteUserRequest,
    MembershipOut, MembershipUpdate, SubscriptionPlanOut,
)

router = APIRouter()


@router.get("", response_model=List[OrganizationOut])
async def list_user_organizations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Organization)
        .join(OrganizationMembership, OrganizationMembership.organization_id == Organization.id)
        .where(
            OrganizationMembership.user_id == current_user.id,
            OrganizationMembership.is_active == True,
            Organization.is_active == True,
        )
    )
    orgs = result.scalars().all()
    return orgs


@router.get("/{org_id}", response_model=OrganizationOut)
async def get_organization(
    org_context=Depends(require_org_role("viewer")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context
    return org


@router.put("/{org_id}", response_model=OrganizationOut)
async def update_organization(
    data: OrganizationUpdate,
    org_context=Depends(require_org_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    org, _, current_user = org_context
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(org, field, value)
    await db.commit()
    await db.refresh(org)
    return org


@router.get("/{org_id}/members", response_model=List[MembershipOut])
async def list_members(
    org_context=Depends(require_org_role("viewer")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context
    result = await db.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == org.id,
            OrganizationMembership.is_active == True,
        )
    )
    return result.scalars().all()


@router.post("/{org_id}/invite")
async def invite_user(
    data: InviteUserRequest,
    org_context=Depends(require_org_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    org, _, current_user = org_context

    token = generate_invitation_token()
    invite = Invitation(
        organization_id=org.id,
        email=data.email.lower(),
        role=data.role,
        token=token,
        invited_by_id=current_user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(invite)
    await db.commit()
    # TODO: Send invitation email
    return {"message": f"Invitation sent to {data.email}", "token": token}


@router.delete("/{org_id}/members/{user_id}")
async def remove_member(
    user_id: UUID,
    org_context=Depends(require_org_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    org, membership, current_user = org_context
    if str(user_id) == str(current_user.id):
        raise ForbiddenError("Cannot remove yourself")

    result = await db.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == org.id,
            OrganizationMembership.user_id == user_id,
        )
    )
    target = result.scalar_one_or_none()
    if not target:
        raise NotFoundError("Membership")
    if target.role == "owner":
        raise ForbiddenError("Cannot remove organization owner")

    target.is_active = False
    await db.commit()
    return {"message": "Member removed"}


@router.put("/{org_id}/members/{user_id}/role")
async def update_member_role(
    user_id: UUID,
    data: MembershipUpdate,
    org_context=Depends(require_org_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    org, _, current_user = org_context
    result = await db.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == org.id,
            OrganizationMembership.user_id == user_id,
        )
    )
    target = result.scalar_one_or_none()
    if not target:
        raise NotFoundError("Membership")
    if target.role == "owner" and data.role != "owner":
        raise ForbiddenError("Cannot demote owner")

    target.role = data.role
    await db.commit()
    return {"message": "Role updated"}


@router.get("/{org_id}/onboarding")
async def get_onboarding_status(
    org_context=Depends(require_org_role("viewer")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context
    return {
        "step": org.onboarding_step,
        "completed": org.onboarding_completed,
        "steps": [
            {"step": 1, "name": "Create Organization", "done": True},
            {"step": 2, "name": "Select Subscription Plan", "done": org.plan_id is not None},
            {"step": 3, "name": "Invite Team Members", "done": org.onboarding_step > 3},
            {"step": 4, "name": "Create Proxmox Connection", "done": org.onboarding_step > 4},
            {"step": 5, "name": "Generate Agent Token", "done": org.onboarding_step > 5},
            {"step": 6, "name": "Install Linux Agent", "done": org.onboarding_step > 6},
            {"step": 7, "name": "Confirm Telemetry", "done": org.onboarding_step > 7},
            {"step": 8, "name": "Configure Alerts", "done": org.onboarding_step > 8},
            {"step": 9, "name": "Enable AI Analysis", "done": org.onboarding_completed},
        ],
    }


@router.post("/{org_id}/onboarding/advance")
async def advance_onboarding(
    org_context=Depends(require_org_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context
    if org.onboarding_step < 9:
        org.onboarding_step += 1
    else:
        org.onboarding_completed = True
    await db.commit()
    return {"step": org.onboarding_step, "completed": org.onboarding_completed}


@router.get("/plans", response_model=List[SubscriptionPlanOut])
async def list_plans(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SubscriptionPlan).where(SubscriptionPlan.is_active == True))
    return result.scalars().all()
