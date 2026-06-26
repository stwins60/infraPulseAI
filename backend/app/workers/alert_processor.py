import asyncio
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.config import settings
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


def get_async_session():
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@celery_app.task(name="app.workers.alert_processor.evaluate_all_alert_rules", queue="alerts")
def evaluate_all_alert_rules():
    asyncio.run(_evaluate_all_rules())


async def _evaluate_all_rules():
    from app.models.alert import AlertRule, Alert
    from app.models.server import Server
    from app.models.metric import Metric
    from sqlalchemy import func

    session_factory = get_async_session()
    async with session_factory() as db:
        rules_result = await db.execute(
            select(AlertRule).where(AlertRule.is_active == True)
        )
        rules = rules_result.scalars().all()

        for rule in rules:
            try:
                await _evaluate_rule(db, rule)
            except Exception as e:
                logger.error("Rule evaluation failed", rule_id=str(rule.id), error=str(e))

        await db.commit()


async def _evaluate_rule(db: AsyncSession, rule):
    from app.models.alert import Alert
    from app.models.metric import Metric
    from app.models.server import Server
    from sqlalchemy import func

    rule_type = rule.rule_type
    threshold = rule.threshold_value
    operator = rule.threshold_operator or ">"

    # Check cooldown
    since_cooldown = datetime.now(timezone.utc) - timedelta(minutes=rule.cooldown_minutes)
    recent_alert_result = await db.execute(
        select(Alert).where(
            Alert.rule_id == rule.id,
            Alert.created_at >= since_cooldown,
            Alert.status.in_(["open", "acknowledged"]),
        ).limit(1)
    )
    if recent_alert_result.scalar_one_or_none():
        return  # Still in cooldown

    # Get latest metrics per server
    since_5m = datetime.now(timezone.utc) - timedelta(minutes=5)

    metric_name_map = {
        "cpu_high": "cpu_percent",
        "memory_high": "memory_percent",
        "disk_high": "disk_percent",
        "load_high": "load_avg_1m",
    }

    metric_name = metric_name_map.get(rule_type)
    if not metric_name:
        return

    # Get latest metrics grouped by server
    result = await db.execute(
        select(Metric.server_id, Metric.value)
        .where(
            Metric.organization_id == rule.organization_id,
            Metric.metric_name == metric_name,
            Metric.timestamp >= since_5m,
            Metric.server_id.isnot(None),
        )
        .order_by(Metric.server_id, Metric.timestamp.desc())
        .distinct(Metric.server_id)
    )
    latest_metrics = result.all()

    for server_id, value in latest_metrics:
        triggered = False
        if operator == ">" and value > threshold:
            triggered = True
        elif operator == ">=" and value >= threshold:
            triggered = True
        elif operator == "<" and value < threshold:
            triggered = True

        if triggered:
            server = await db.get(Server, server_id)
            server_name = server.hostname if server else "Unknown"

            alert = Alert(
                organization_id=rule.organization_id,
                rule_id=rule.id,
                server_id=server_id,
                title=f"{rule_type.replace('_', ' ').title()} on {server_name}",
                description=f"{metric_name} is {value:.1f}% (threshold: {threshold}%)",
                severity=rule.severity,
                status="open",
                source_type="rule",
                rule_type=rule_type,
                trigger_value=value,
                threshold_value=threshold,
                trigger_data={"metric": metric_name, "value": value, "threshold": threshold},
            )
            db.add(alert)
            logger.info("Alert created", rule=rule.name, server=server_name, value=value)


@celery_app.task(name="app.workers.alert_processor.check_agent_heartbeats", queue="alerts")
def check_agent_heartbeats():
    asyncio.run(_check_heartbeats())


async def _check_heartbeats():
    from app.models.server import Server, ServerAgent
    from app.models.alert import Alert, AlertRule

    timeout = timedelta(seconds=settings.AGENT_HEARTBEAT_TIMEOUT_SECONDS)
    cutoff = datetime.now(timezone.utc) - timeout

    session_factory = get_async_session()
    async with session_factory() as db:
        # Find agents that haven't heartbeated recently
        result = await db.execute(
            select(ServerAgent).where(
                ServerAgent.is_active == True,
                ServerAgent.last_heartbeat_at < cutoff,
            )
        )
        stale_agents = result.scalars().all()

        for agent in stale_agents:
            server = await db.get(Server, agent.server_id)
            if not server:
                continue

            # Check if we already have an open offline alert
            existing = await db.execute(
                select(Alert).where(
                    Alert.server_id == agent.server_id,
                    Alert.rule_type == "agent_offline",
                    Alert.status == "open",
                ).limit(1)
            )
            if existing.scalar_one_or_none():
                continue

            server.status = "offline"
            alert = Alert(
                organization_id=agent.organization_id,
                server_id=agent.server_id,
                title=f"Agent offline: {server.hostname}",
                description=f"No heartbeat received in {settings.AGENT_HEARTBEAT_TIMEOUT_SECONDS} seconds",
                severity="high",
                status="open",
                source_type="heartbeat",
                rule_type="agent_offline",
                trigger_data={"last_heartbeat": agent.last_heartbeat_at.isoformat() if agent.last_heartbeat_at else None},
            )
            db.add(alert)
            logger.warning("Agent offline alert created", server=server.hostname)

        await db.commit()


@celery_app.task(name="app.workers.alert_processor.cleanup_old_metrics", queue="default")
def cleanup_old_metrics():
    asyncio.run(_cleanup_metrics())


async def _cleanup_metrics():
    from app.models.metric import Metric
    from app.models.log_entry import LogEntry
    from app.models.organization import Organization, SubscriptionPlan

    session_factory = get_async_session()
    async with session_factory() as db:
        # Get all orgs and their retention policies
        orgs_result = await db.execute(
            select(Organization).where(Organization.is_active == True)
        )
        orgs = orgs_result.scalars().all()

        for org in orgs:
            # Default retention
            metric_days = 90
            log_days = 30

            if org.plan_id:
                plan = await db.get(SubscriptionPlan, org.plan_id)
                if plan:
                    metric_days = plan.max_metric_retention_days
                    log_days = plan.max_log_retention_days

            metric_cutoff = datetime.now(timezone.utc) - timedelta(days=metric_days)
            log_cutoff = datetime.now(timezone.utc) - timedelta(days=log_days)

            # Delete old metrics
            await db.execute(
                delete(Metric).where(
                    Metric.organization_id == org.id,
                    Metric.timestamp < metric_cutoff,
                )
            )

            # Delete old logs
            await db.execute(
                delete(LogEntry).where(
                    LogEntry.organization_id == org.id,
                    LogEntry.timestamp < log_cutoff,
                )
            )

        await db.commit()
        logger.info("Metrics and logs cleanup completed")
