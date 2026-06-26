"""
Seed data script for InfraPulse AI demo mode.
Creates platform admin, demo organization, and sample infrastructure data.
"""
import asyncio
import random
import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select

logger = structlog.get_logger(__name__)


async def seed_data():
    from app.config import settings
    if not settings.SEED_DEMO_DATA:
        return

    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        await _seed_subscription_plans(db)
        await _seed_platform_admin(db)
        if settings.DEMO_MODE:
            await _seed_demo_organization(db)
        await db.commit()
    await engine.dispose()
    logger.info("Seed data completed")


async def _seed_subscription_plans(db: AsyncSession):
    from app.models.organization import SubscriptionPlan
    result = await db.execute(select(SubscriptionPlan).limit(1))
    if result.scalar_one_or_none():
        return  # Already seeded

    plans = [
        SubscriptionPlan(name="free", display_name="Free Tier", max_servers=5, max_users=3, max_proxmox_connections=1, max_log_retention_days=7, max_metric_retention_days=30, price_monthly=None),
        SubscriptionPlan(name="starter", display_name="Starter", max_servers=20, max_users=10, max_proxmox_connections=3, max_log_retention_days=30, max_metric_retention_days=90, ai_analysis_enabled=True, price_monthly=49.00),
        SubscriptionPlan(name="professional", display_name="Professional", max_servers=100, max_users=50, max_proxmox_connections=10, max_log_retention_days=90, max_metric_retention_days=365, ai_analysis_enabled=True, advanced_alerting=True, price_monthly=149.00),
        SubscriptionPlan(name="enterprise", display_name="Enterprise", max_servers=999, max_users=999, max_proxmox_connections=999, max_log_retention_days=365, max_metric_retention_days=730, ai_analysis_enabled=True, advanced_alerting=True, price_monthly=499.00),
    ]
    db.add_all(plans)
    await db.flush()
    logger.info("Subscription plans seeded")


async def _seed_platform_admin(db: AsyncSession):
    from app.models.user import User
    from app.core.security import hash_password
    from app.config import settings

    result = await db.execute(select(User).where(User.email == settings.PLATFORM_ADMIN_EMAIL))
    if result.scalar_one_or_none():
        return

    admin = User(
        email=settings.PLATFORM_ADMIN_EMAIL,
        hashed_password=hash_password(settings.PLATFORM_ADMIN_PASSWORD),
        full_name=settings.PLATFORM_ADMIN_NAME,
        is_active=True,
        is_verified=True,
        is_platform_admin=True,
    )
    db.add(admin)
    await db.flush()
    logger.info("Platform admin created", email=settings.PLATFORM_ADMIN_EMAIL)


async def _seed_demo_organization(db: AsyncSession):
    from app.models.organization import Organization, OrganizationMembership, SubscriptionPlan
    from app.models.user import User
    from app.models.server import Server, ServerAgent, AgentRegistrationToken
    from app.models.alert import AlertRule, Alert
    from app.models.incident import Incident
    from app.models.metric import Metric
    from app.models.log_entry import LogEntry
    from app.models.notification import NotificationChannel
    from app.core.security import hash_password
    import secrets

    result = await db.execute(select(Organization).where(Organization.slug == "acme-corp-demo"))
    if result.scalar_one_or_none():
        return

    # Get professional plan
    plan_result = await db.execute(select(SubscriptionPlan).where(SubscriptionPlan.name == "professional"))
    plan = plan_result.scalar_one_or_none()

    # Create demo org
    org = Organization(
        name="Acme Corp (Demo)",
        slug="acme-corp-demo",
        description="Demo organization showing InfraPulse AI capabilities",
        plan_id=plan.id if plan else None,
        is_active=True,
        onboarding_completed=True,
        onboarding_step=9,
        contact_email="demo@acme-corp.example.com",
        ai_provider_config={"provider": "groq", "model": "llama-3.3-70b-versatile"},
    )
    db.add(org)
    await db.flush()

    # Create demo users
    demo_password = hash_password("Demo123!")

    owner = User(email="owner@acme-corp.example.com", hashed_password=demo_password, full_name="Alice Johnson", is_active=True, is_verified=True)
    admin = User(email="admin@acme-corp.example.com", hashed_password=demo_password, full_name="Bob Smith", is_active=True, is_verified=True)
    operator = User(email="ops@acme-corp.example.com", hashed_password=demo_password, full_name="Charlie Brown", is_active=True, is_verified=True)
    viewer = User(email="viewer@acme-corp.example.com", hashed_password=demo_password, full_name="Diana Prince", is_active=True, is_verified=True)

    db.add_all([owner, admin, operator, viewer])
    await db.flush()

    now = datetime.now(timezone.utc)
    memberships = [
        OrganizationMembership(organization_id=org.id, user_id=owner.id, role="owner", accepted_at=now),
        OrganizationMembership(organization_id=org.id, user_id=admin.id, role="admin", accepted_at=now),
        OrganizationMembership(organization_id=org.id, user_id=operator.id, role="operator", accepted_at=now),
        OrganizationMembership(organization_id=org.id, user_id=viewer.id, role="viewer", accepted_at=now),
    ]
    db.add_all(memberships)

    # Create demo servers
    server_configs = [
        ("web-prod-01", "10.0.1.10", "online", "production", 85),
        ("web-prod-02", "10.0.1.11", "online", "production", 72),
        ("db-prod-01", "10.0.2.10", "online", "production", 91),
        ("db-prod-02", "10.0.2.11", "warning", "production", 45),
        ("cache-prod-01", "10.0.3.10", "online", "production", 88),
        ("worker-prod-01", "10.0.4.10", "critical", "production", 20),
        ("worker-prod-02", "10.0.4.11", "online", "production", 78),
        ("staging-web-01", "10.1.1.10", "online", "staging", 65),
        ("dev-server-01", "10.2.1.10", "offline", "development", 0),
        ("monitoring-01", "10.0.5.10", "online", "production", 95),
    ]

    servers = []
    for hostname, ip, status, env, health in server_configs:
        server = Server(
            organization_id=org.id,
            hostname=hostname,
            display_name=hostname.replace("-", " ").title(),
            ip_addresses=[ip],
            os_type="Ubuntu",
            os_version="22.04 LTS",
            kernel_version="5.15.0-91-generic",
            cpu_count=random.choice([2, 4, 8, 16]),
            cpu_model="Intel Xeon E5-2686 v4",
            memory_total_bytes=random.choice([4, 8, 16, 32]) * 1024 ** 3,
            environment=env,
            status=status,
            health_score=health,
            tags=[env, "linux", random.choice(["web", "database", "cache", "worker", "monitoring"])],
            region="us-east-1",
            owner_team="Infrastructure",
            last_seen_at=now - timedelta(seconds=random.randint(0, 300)),
        )
        servers.append(server)
        db.add(server)

    await db.flush()

    # Add server agents to online servers
    for server in servers:
        if server.status != "offline":
            agent_token = f"ipa_at_{secrets.token_urlsafe(32)}"
            import hashlib
            agent = ServerAgent(
                server_id=server.id,
                organization_id=org.id,
                agent_token_hash=hashlib.sha256(agent_token.encode()).hexdigest(),
                agent_version="1.0.0",
                is_active=True,
                last_heartbeat_at=now - timedelta(seconds=random.randint(0, 60)),
            )
            db.add(agent)

    # Generate historical metrics (last 24 hours)
    for server in servers[:5]:  # Only for first 5 servers to keep it manageable
        for hours_ago in range(24, 0, -1):
            for minutes in [0, 15, 30, 45]:
                ts = now - timedelta(hours=hours_ago, minutes=minutes)
                base_cpu = random.uniform(20, 80)
                base_mem = random.uniform(40, 90)
                base_disk = random.uniform(30, 75)

                metrics = [
                    Metric(organization_id=org.id, server_id=server.id, source_type="agent", metric_name="cpu_percent", value=base_cpu + random.uniform(-10, 10), unit="%", timestamp=ts),
                    Metric(organization_id=org.id, server_id=server.id, source_type="agent", metric_name="memory_percent", value=base_mem + random.uniform(-5, 5), unit="%", timestamp=ts),
                    Metric(organization_id=org.id, server_id=server.id, source_type="agent", metric_name="disk_percent", value=base_disk + random.uniform(-3, 3), unit="%", timestamp=ts),
                    Metric(organization_id=org.id, server_id=server.id, source_type="agent", metric_name="load_avg_1m", value=random.uniform(0.5, 4.0), timestamp=ts),
                ]
                db.add_all(metrics)

    # Generate sample log entries
    log_messages = [
        ("error", "syslog", "kernel", "OOM killer invoked - process 'java' killed"),
        ("warning", "auth", "sshd", "Failed password for invalid user admin from 45.33.32.156 port 12345"),
        ("error", "app", "nginx", "upstream timed out (110: Connection timed out) while reading response header"),
        ("info", "syslog", "systemd", "Starting PostgreSQL database server"),
        ("critical", "app", "postgresql", "could not connect to the primary server: could not connect to server"),
        ("warning", "syslog", "kernel", "nf_conntrack: table full, dropping packet"),
        ("error", "app", "docker", "Container web-app exited with code 137 (OOM)"),
        ("info", "auth", "sudo", "alice : TTY=pts/0 ; USER=root ; COMMAND=/bin/systemctl restart nginx"),
        ("warning", "app", "redis", "MISCONF Redis is configured to save RDB snapshots, but it is currently not able to persist on disk"),
        ("error", "syslog", "disk", "EXT4-fs error (device sda1): ext4_find_entry:1455: inode #524288: comm java: reading directory lblock 0"),
    ]

    for server in servers[:6]:
        for i, (severity, source, service, message) in enumerate(log_messages * 5):
            ts = now - timedelta(minutes=random.randint(1, 1440))
            db.add(LogEntry(
                organization_id=org.id,
                server_id=server.id,
                severity=severity,
                source=source,
                service=service,
                message=message,
                timestamp=ts,
            ))

    # Create alert rules
    alert_rules = [
        AlertRule(organization_id=org.id, name="High CPU Usage", rule_type="cpu_high", severity="high", condition={"metric": "cpu_percent"}, threshold_value=85.0, threshold_operator=">", is_active=True, ai_analysis_enabled=True, created_by_id=admin.id),
        AlertRule(organization_id=org.id, name="Critical Memory Usage", rule_type="memory_high", severity="critical", condition={"metric": "memory_percent"}, threshold_value=95.0, threshold_operator=">", is_active=True, ai_analysis_enabled=True, created_by_id=admin.id),
        AlertRule(organization_id=org.id, name="Disk Space Warning", rule_type="disk_high", severity="medium", condition={"metric": "disk_percent"}, threshold_value=80.0, threshold_operator=">", is_active=True, created_by_id=admin.id),
        AlertRule(organization_id=org.id, name="Disk Space Critical", rule_type="disk_high", severity="critical", condition={"metric": "disk_percent"}, threshold_value=95.0, threshold_operator=">", is_active=True, ai_analysis_enabled=True, created_by_id=admin.id),
        AlertRule(organization_id=org.id, name="Agent Offline", rule_type="agent_offline", severity="high", condition={"timeout_seconds": 300}, is_active=True, created_by_id=admin.id),
    ]
    db.add_all(alert_rules)
    await db.flush()

    # Create sample alerts
    sample_alerts = [
        Alert(organization_id=org.id, rule_id=alert_rules[0].id, server_id=servers[2].id, title="High CPU Usage on db-prod-01", description="CPU usage reached 92.3%", severity="high", status="open", source_type="rule", rule_type="cpu_high", trigger_value=92.3, threshold_value=85.0, created_at=now - timedelta(hours=2)),
        Alert(organization_id=org.id, rule_id=alert_rules[1].id, server_id=servers[5].id, title="Critical Memory Usage on worker-prod-01", description="Memory usage reached 97.1%", severity="critical", status="open", source_type="rule", rule_type="memory_high", trigger_value=97.1, threshold_value=95.0, created_at=now - timedelta(hours=1)),
        Alert(organization_id=org.id, rule_id=alert_rules[2].id, server_id=servers[1].id, title="Disk Space Warning on web-prod-02", description="Disk usage reached 82.5%", severity="medium", status="acknowledged", source_type="rule", rule_type="disk_high", trigger_value=82.5, threshold_value=80.0, acknowledged_at=now - timedelta(minutes=30), acknowledged_by_id=operator.id, created_at=now - timedelta(hours=5)),
        Alert(organization_id=org.id, server_id=servers[8].id, title="Agent Offline: dev-server-01", description="No heartbeat received in 300 seconds", severity="high", status="open", source_type="heartbeat", rule_type="agent_offline", created_at=now - timedelta(hours=3)),
        Alert(organization_id=org.id, rule_id=alert_rules[0].id, server_id=servers[0].id, title="High CPU Usage on web-prod-01", description="CPU usage reached 88.7% for 5 minutes", severity="high", status="resolved", source_type="rule", rule_type="cpu_high", trigger_value=88.7, resolved_at=now - timedelta(hours=6), created_at=now - timedelta(hours=8)),
    ]
    db.add_all(sample_alerts)
    await db.flush()

    # Create a sample incident
    incident = Incident(
        organization_id=org.id,
        title="Production Worker Memory Exhaustion",
        description="worker-prod-01 is experiencing critical memory exhaustion causing service degradation",
        severity="critical",
        status="open",
        created_by_id=operator.id,
        timeline=[
            {"time": (now - timedelta(hours=1)).isoformat(), "event": "Incident detected - memory usage at 97%", "user": str(operator.id)},
            {"time": (now - timedelta(minutes=45)).isoformat(), "event": "Investigating root cause - checking application logs", "user": str(operator.id)},
            {"time": (now - timedelta(minutes=30)).isoformat(), "event": "Identified: Java heap space exhaustion. Memory leak in application", "user": str(admin.id)},
        ],
    )
    incident.alerts.append(sample_alerts[1])
    db.add(incident)

    # Create notification channel (Slack - no real webhook)
    nc = NotificationChannel(
        organization_id=org.id,
        name="Production Slack Alerts",
        channel_type="slack",
        config={"channel": "#alerts-prod"},
        is_active=True,
    )
    db.add(nc)

    await db.flush()
    logger.info("Demo organization seeded", org_slug=org.slug, servers=len(servers))


if __name__ == "__main__":
    asyncio.run(seed_data())
