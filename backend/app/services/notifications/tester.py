from typing import Tuple
import structlog

logger = structlog.get_logger(__name__)


async def test_notification_channel(channel) -> Tuple[bool, str]:
    """Test a notification channel by sending a test message."""
    from app.services.encryption_service import decrypt

    channel_type = channel.channel_type
    config = channel.config or {}

    # Decrypt sensitive config
    sensitive = {}
    if channel.config_encrypted:
        try:
            import ast
            raw = decrypt(channel.config_encrypted)
            sensitive = ast.literal_eval(raw)
        except Exception:
            pass

    if channel_type == "slack":
        webhook_url = sensitive.get("webhook_url") or config.get("webhook_url")
        if not webhook_url:
            return False, "Slack webhook URL not configured"
        from app.services.notifications.slack import send_slack_notification
        payload = {
            "text": "✅ InfraPulse AI — Test notification. Your Slack integration is working correctly.",
            "blocks": [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "✅ *InfraPulse AI* — Test notification\nYour Slack integration is working correctly."},
                }
            ],
        }
        return await send_slack_notification(webhook_url, payload)

    elif channel_type == "email":
        from app.services.notifications.email import send_email
        to_addresses = config.get("to_addresses", [])
        if not to_addresses:
            return False, "No recipient email addresses configured"
        smtp_config = {
            "smtp_host": config.get("smtp_host"),
            "smtp_port": config.get("smtp_port"),
            "smtp_username": sensitive.get("smtp_username"),
            "smtp_password": sensitive.get("smtp_password"),
        }
        return await send_email(
            to_addresses,
            "InfraPulse AI — Test Notification",
            "<p>This is a test notification from InfraPulse AI. Your email integration is working correctly.</p>",
            smtp_config,
        )

    elif channel_type == "webhook":
        import aiohttp
        webhook_url = sensitive.get("webhook_url") or config.get("webhook_url")
        if not webhook_url:
            return False, "Webhook URL not configured"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    webhook_url,
                    json={"message": "InfraPulse AI test notification", "status": "test"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status < 400:
                        return True, f"Webhook returned {resp.status}"
                    return False, f"Webhook returned error status {resp.status}"
        except Exception as e:
            return False, f"Webhook error: {str(e)}"

    return False, f"Unknown channel type: {channel_type}"
