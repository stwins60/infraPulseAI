from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.core.dependencies import require_org_role, get_platform_admin
from app.models.organization import AuditLog

router = APIRouter()


@router.get("", response_model=dict)
async def get_audit_logs(
    org_context=Depends(require_org_role("admin")),
    db: AsyncSession = Depends(get_db),
    action: Optional[str] = Query(None),
    user_id: Optional[UUID] = Query(None),
    days: int = Query(30, le=90),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
):
    org, _, _ = org_context
    since = datetime.now(timezone.utc) - timedelta(days=days)

    query = select(AuditLog).where(
        AuditLog.organization_id == org.id,
        AuditLog.created_at >= since,
    )
    if action:
        query = query.where(AuditLog.action.ilike(f"%{action}%"))
    if user_id:
        query = query.where(AuditLog.user_id == user_id)

    query = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    logs = result.scalars().all()

    return {
        "logs": [
            {
                "id": str(log.id),
                "action": log.action,
                "user_id": str(log.user_id) if log.user_id else None,
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "details": log.details,
                "ip_address": log.ip_address,
                "success": log.success,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ]
    }
