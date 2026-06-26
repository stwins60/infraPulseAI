import asyncio
from datetime import datetime, timezone
from typing import Optional

import aiohttp
import structlog

logger = structlog.get_logger(__name__)


async def send_slack_notification(webhook_url: str, payload: dict) -> tuple[bool, str]:
    """Send a Slack notification via incoming webhook."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                webhook_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    return True, "Notification sent successfully"
                else:
                    text = await resp.text()
                    return False, f"Slack API error {resp.status}: {text}"
    except Exception as e:
        logger.error("Slack notification failed", error=str(e))
        return False, f"Error: {str(e)}"


def build_alert_slack_payload(
    alert,
    server_name: Optional[str],
    org_name: str,
    dashboard_url: str,
    ai_summary: Optional[str] = None,
) -> dict:
    """Build a rich Slack Block Kit payload for an alert."""
    severity_colors = {
        "critical": "#FF0000",
        "high": "#FF6600",
        "medium": "#FFA500",
        "low": "#FFFF00",
        "info": "#0099FF",
    }
    color = severity_colors.get(alert.severity, "#808080")

    severity_emoji = {
        "critical": ":red_circle:",
        "high": ":orange_circle:",
        "medium": ":yellow_circle:",
        "low": ":white_circle:",
        "info": ":blue_circle:",
    }.get(alert.severity, ":white_circle:")

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{severity_emoji} {alert.severity.upper()} Alert — InfraPulse AI"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*{alert.title}*"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Organization:*\n{org_name}"},
                {"type": "mrkdwn", "text": f"*Severity:*\n{alert.severity.upper()}"},
                {"type": "mrkdwn", "text": f"*Server:*\n{server_name or 'N/A'}"},
                {"type": "mrkdwn", "text": f"*Rule Type:*\n{alert.rule_type or 'N/A'}"},
            ],
        },
    ]

    if alert.trigger_value is not None:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Triggered Value:* `{alert.trigger_value}` (threshold: `{alert.threshold_value}`)"},
        })

    if ai_summary:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*:robot_face: AI Analysis:*\n{ai_summary}"},
        })

    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "View Alert"},
                "url": f"{dashboard_url}/alerts/{alert.id}",
                "style": "danger" if alert.severity in ("critical", "high") else "primary",
            }
        ],
    })

    return {
        "attachments": [{"color": color, "blocks": blocks}],
        "text": f"Alert: {alert.title}",
    }
