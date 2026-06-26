from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.core.dependencies import require_org_role
from app.core.exceptions import NotFoundError
from app.models.notification import NotificationChannel, NotificationPolicy
from app.schemas.notification import (
    NotificationChannelCreate, NotificationChannelOut,
    NotificationPolicyCreate, NotificationPolicyOut,
)
from app.services.notifications.tester import test_notification_channel
from app.services.encryption_service import encrypt

router = APIRouter()


@router.get("/channels", response_model=List[NotificationChannelOut])
async def list_channels(
    org_context=Depends(require_org_role("viewer")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context
    result = await db.execute(
        select(NotificationChannel).where(NotificationChannel.organization_id == org.id)
    )
    return result.scalars().all()


@router.post("/channels", response_model=NotificationChannelOut, status_code=201)
async def create_channel(
    data: NotificationChannelCreate,
    org_context=Depends(require_org_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context

    # Separate sensitive config (webhooks, passwords, tokens)
    sensitive_fields = {"webhook_url", "smtp_password", "token", "api_key"}
    sensitive = {k: v for k, v in data.config.items() if k in sensitive_fields}
    safe_config = {k: v for k, v in data.config.items() if k not in sensitive_fields}

    channel = NotificationChannel(
        organization_id=org.id,
        name=data.name,
        channel_type=data.channel_type,
        config=safe_config,
        config_encrypted=encrypt(str(sensitive)) if sensitive else None,
        is_active=data.is_active,
    )
    db.add(channel)
    await db.commit()
    await db.refresh(channel)
    return channel


@router.put("/channels/{channel_id}", response_model=NotificationChannelOut)
async def update_channel(
    channel_id: UUID,
    data: NotificationChannelCreate,
    org_context=Depends(require_org_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context
    channel = await db.get(NotificationChannel, channel_id)
    if not channel or channel.organization_id != org.id:
        raise NotFoundError("Notification channel")

    channel.name = data.name
    channel.channel_type = data.channel_type
    channel.config = data.config
    channel.is_active = data.is_active
    await db.commit()
    await db.refresh(channel)
    return channel


@router.delete("/channels/{channel_id}")
async def delete_channel(
    channel_id: UUID,
    org_context=Depends(require_org_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context
    channel = await db.get(NotificationChannel, channel_id)
    if not channel or channel.organization_id != org.id:
        raise NotFoundError("Notification channel")
    await db.delete(channel)
    await db.commit()
    return {"message": "Channel deleted"}


@router.post("/channels/{channel_id}/test")
async def test_channel(
    channel_id: UUID,
    org_context=Depends(require_org_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context
    channel = await db.get(NotificationChannel, channel_id)
    if not channel or channel.organization_id != org.id:
        raise NotFoundError("Notification channel")

    success, message = await test_notification_channel(channel)
    channel.last_tested_at = datetime.now(timezone.utc)
    channel.last_test_success = success
    await db.commit()
    return {"success": success, "message": message}


@router.get("/policies", response_model=List[NotificationPolicyOut])
async def list_policies(
    org_context=Depends(require_org_role("viewer")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context
    result = await db.execute(
        select(NotificationPolicy).where(NotificationPolicy.organization_id == org.id)
    )
    return result.scalars().all()


@router.post("/policies", response_model=NotificationPolicyOut, status_code=201)
async def create_policy(
    data: NotificationPolicyCreate,
    org_context=Depends(require_org_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context
    policy = NotificationPolicy(
        organization_id=org.id,
        name=data.name,
        is_active=data.is_active,
        rules=data.rules,
    )
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    return policy
