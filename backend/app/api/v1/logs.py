from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, text
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.core.dependencies import require_org_role
from app.core.exceptions import NotFoundError
from app.models.log_entry import LogEntry, SavedSearch
from app.models.server import Server
from app.schemas.log_entry import LogEntryOut, LogSearchParams, SavedSearchCreate, SavedSearchOut

router = APIRouter()

SEVERITY_LEVELS = {"debug": 0, "info": 1, "warning": 2, "error": 3, "critical": 4}


@router.get("", response_model=dict)
async def search_logs(
    org_context=Depends(require_org_role("viewer")),
    db: AsyncSession = Depends(get_db),
    q: Optional[str] = Query(None, description="Full-text search query"),
    server_id: Optional[UUID] = Query(None),
    severity: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    service: Optional[str] = Query(None),
    application: Optional[str] = Query(None),
    environment: Optional[str] = Query(None),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    use_regex: bool = Query(False),
):
    org, _, _ = org_context

    query = select(LogEntry).where(LogEntry.organization_id == org.id)

    if server_id:
        query = query.where(LogEntry.server_id == server_id)
    if severity:
        query = query.where(LogEntry.severity == severity)
    if source:
        query = query.where(LogEntry.source == source)
    if service:
        query = query.where(LogEntry.service.ilike(f"%{service}%"))
    if application:
        query = query.where(LogEntry.application.ilike(f"%{application}%"))
    if start_time:
        query = query.where(LogEntry.timestamp >= start_time)
    if end_time:
        query = query.where(LogEntry.timestamp <= end_time)
    else:
        # Default to last 24h
        query = query.where(LogEntry.timestamp >= datetime.now(timezone.utc) - timedelta(hours=24))

    if q:
        if use_regex:
            query = query.where(LogEntry.message.op("~")(q))
        else:
            query = query.where(LogEntry.message.ilike(f"%{q}%"))

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(LogEntry.timestamp.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    logs = result.scalars().all()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "logs": [
            {
                "id": str(log.id),
                "server_id": str(log.server_id) if log.server_id else None,
                "severity": log.severity,
                "source": log.source,
                "service": log.service,
                "application": log.application,
                "message": log.message,
                "timestamp": log.timestamp.isoformat(),
                "metadata": log.log_metadata,
            }
            for log in logs
        ],
    }


@router.get("/stats")
async def get_log_stats(
    org_context=Depends(require_org_role("viewer")),
    db: AsyncSession = Depends(get_db),
    hours: int = Query(24, le=168),
):
    org, _, _ = org_context
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    result = await db.execute(
        select(LogEntry.severity, func.count(LogEntry.id))
        .where(LogEntry.organization_id == org.id, LogEntry.timestamp >= since)
        .group_by(LogEntry.severity)
    )
    stats = {row[0]: row[1] for row in result.all()}
    return {"since": since.isoformat(), "by_severity": stats, "total": sum(stats.values())}


@router.post("/saved-searches", response_model=SavedSearchOut, status_code=201)
async def create_saved_search(
    data: SavedSearchCreate,
    org_context=Depends(require_org_role("viewer")),
    db: AsyncSession = Depends(get_db),
):
    org, _, current_user = org_context
    ss = SavedSearch(
        organization_id=org.id,
        user_id=current_user.id,
        name=data.name,
        query_params=data.query_params,
        is_shared=data.is_shared,
    )
    db.add(ss)
    await db.commit()
    await db.refresh(ss)
    return ss


@router.get("/saved-searches", response_model=List[SavedSearchOut])
async def list_saved_searches(
    org_context=Depends(require_org_role("viewer")),
    db: AsyncSession = Depends(get_db),
):
    org, _, current_user = org_context
    result = await db.execute(
        select(SavedSearch).where(
            SavedSearch.organization_id == org.id,
            or_(SavedSearch.user_id == current_user.id, SavedSearch.is_shared == True),
        ).order_by(SavedSearch.created_at.desc())
    )
    return result.scalars().all()
