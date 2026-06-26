from celery import Celery
from app.config import settings

celery_app = Celery(
    "infrapulse",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.workers.proxmox_poller",
        "app.workers.alert_processor",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "poll-proxmox-connections": {
            "task": "app.workers.proxmox_poller.poll_all_proxmox_connections",
            "schedule": 60.0,  # Every 60 seconds
            "options": {"queue": "proxmox"},
        },
        "evaluate-alert-rules": {
            "task": "app.workers.alert_processor.evaluate_all_alert_rules",
            "schedule": 30.0,  # Every 30 seconds
            "options": {"queue": "alerts"},
        },
        "check-agent-heartbeats": {
            "task": "app.workers.alert_processor.check_agent_heartbeats",
            "schedule": 60.0,  # Every 60 seconds
            "options": {"queue": "alerts"},
        },
        "cleanup-old-metrics": {
            "task": "app.workers.alert_processor.cleanup_old_metrics",
            "schedule": 3600.0,  # Every hour
            "options": {"queue": "default"},
        },
    },
    task_routes={
        "app.workers.proxmox_poller.*": {"queue": "proxmox"},
        "app.workers.alert_processor.*": {"queue": "alerts"},
    },
)
