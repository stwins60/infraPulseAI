from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text

from app.database import get_db
from app.core.dependencies import require_org_role
from app.models.metric import Metric
from app.models.server import Server
from app.schemas.metric import MetricOut, MetricQuery, MetricSeries

router = APIRouter()

TIME_RANGES = {
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


@router.get("/servers/{server_id}", response_model=List[MetricSeries])
async def get_server_metrics(
    server_id: UUID,
    metric_names: str = Query(..., description="Comma-separated metric names"),
    time_range: str = Query("1h", enum=list(TIME_RANGES.keys())),
    org_context=Depends(require_org_role("viewer")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context
    names = [n.strip() for n in metric_names.split(",")]
    since = datetime.now(timezone.utc) - TIME_RANGES[time_range]

    result = await db.execute(
        select(Metric).where(
            Metric.organization_id == org.id,
            Metric.server_id == server_id,
            Metric.metric_name.in_(names),
            Metric.timestamp >= since,
        ).order_by(Metric.timestamp)
    )
    metrics = result.scalars().all()

    # Group by metric name
    series: dict[str, list] = {}
    for m in metrics:
        if m.metric_name not in series:
            series[m.metric_name] = []
        series[m.metric_name].append({"timestamp": m.timestamp.isoformat(), "value": m.value})

    return [
        MetricSeries(name=name, data=points)
        for name, points in series.items()
    ]


@router.get("/summary")
async def get_metrics_summary(
    org_context=Depends(require_org_role("viewer")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context
    since = datetime.now(timezone.utc) - timedelta(minutes=5)

    # Get latest metrics per server
    result = await db.execute(
        text("""
            SELECT DISTINCT ON (server_id, metric_name)
                server_id, metric_name, value, timestamp
            FROM metrics
            WHERE organization_id = :org_id
            AND timestamp >= :since
            AND metric_name IN ('cpu_percent', 'memory_percent', 'disk_percent')
            ORDER BY server_id, metric_name, timestamp DESC
        """),
        {"org_id": str(org.id), "since": since},
    )
    rows = result.mappings().all()

    summary = {"cpu": [], "memory": [], "disk": []}
    for row in rows:
        if row["metric_name"] == "cpu_percent":
            summary["cpu"].append({"server_id": str(row["server_id"]), "value": row["value"]})
        elif row["metric_name"] == "memory_percent":
            summary["memory"].append({"server_id": str(row["server_id"]), "value": row["value"]})
        elif row["metric_name"] == "disk_percent":
            summary["disk"].append({"server_id": str(row["server_id"]), "value": row["value"]})

    # Compute averages
    def avg(vals):
        return round(sum(v["value"] for v in vals) / len(vals), 1) if vals else 0

    return {
        "avg_cpu": avg(summary["cpu"]),
        "avg_memory": avg(summary["memory"]),
        "avg_disk": avg(summary["disk"]),
        "top_cpu": sorted(summary["cpu"], key=lambda x: x["value"], reverse=True)[:5],
        "top_memory": sorted(summary["memory"], key=lambda x: x["value"], reverse=True)[:5],
        "top_disk": sorted(summary["disk"], key=lambda x: x["value"], reverse=True)[:5],
    }
