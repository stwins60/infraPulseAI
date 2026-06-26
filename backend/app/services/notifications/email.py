import aiosmtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

import structlog
from jinja2 import Template

from app.config import settings

logger = structlog.get_logger(__name__)

ALERT_EMAIL_HTML = """
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>InfraPulse AI Alert</title></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f1117; color: #e1e4e8; padding: 20px;">
  <div style="max-width: 600px; margin: 0 auto; background: #1a1d27; border-radius: 12px; overflow: hidden;">
    <div style="background: linear-gradient(135deg, #1a2744, #0d1525); padding: 24px; border-bottom: 1px solid #2d3748;">
      <h1 style="margin: 0; font-size: 20px; color: #fff;">⚡ InfraPulse AI</h1>
      <p style="margin: 4px 0 0; color: #8892a4; font-size: 13px;">Infrastructure Alert Notification</p>
    </div>
    <div style="padding: 24px;">
      <div style="background: {{ severity_bg }}; border-left: 4px solid {{ severity_color }}; padding: 16px; border-radius: 6px; margin-bottom: 20px;">
        <p style="margin: 0; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; color: {{ severity_color }}; font-weight: 700;">{{ severity }}</p>
        <h2 style="margin: 8px 0 0; font-size: 18px; color: #fff;">{{ title }}</h2>
      </div>
      <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
        <tr>
          <td style="padding: 8px 0; border-bottom: 1px solid #2d3748; color: #8892a4; font-size: 13px; width: 40%;">Organization</td>
          <td style="padding: 8px 0; border-bottom: 1px solid #2d3748; color: #e1e4e8; font-size: 13px;">{{ org_name }}</td>
        </tr>
        <tr>
          <td style="padding: 8px 0; border-bottom: 1px solid #2d3748; color: #8892a4; font-size: 13px;">Server</td>
          <td style="padding: 8px 0; border-bottom: 1px solid #2d3748; color: #e1e4e8; font-size: 13px;">{{ server_name }}</td>
        </tr>
        <tr>
          <td style="padding: 8px 0; border-bottom: 1px solid #2d3748; color: #8892a4; font-size: 13px;">Alert Type</td>
          <td style="padding: 8px 0; border-bottom: 1px solid #2d3748; color: #e1e4e8; font-size: 13px;">{{ rule_type }}</td>
        </tr>
        {% if trigger_value %}<tr>
          <td style="padding: 8px 0; border-bottom: 1px solid #2d3748; color: #8892a4; font-size: 13px;">Value</td>
          <td style="padding: 8px 0; border-bottom: 1px solid #2d3748; color: #e1e4e8; font-size: 13px;">{{ trigger_value }}</td>
        </tr>{% endif %}
        <tr>
          <td style="padding: 8px 0; color: #8892a4; font-size: 13px;">Time</td>
          <td style="padding: 8px 0; color: #e1e4e8; font-size: 13px;">{{ triggered_at }}</td>
        </tr>
      </table>
      {% if ai_summary %}
      <div style="background: #1e2535; border: 1px solid #2d3748; border-radius: 6px; padding: 16px; margin-bottom: 20px;">
        <p style="margin: 0 0 8px; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; color: #7c8db5;">🤖 AI Analysis</p>
        <p style="margin: 0; color: #c1c8d4; font-size: 14px;">{{ ai_summary }}</p>
      </div>
      {% endif %}
      <div style="text-align: center;">
        <a href="{{ dashboard_url }}" style="display: inline-block; background: #3b82f6; color: #fff; padding: 12px 28px; border-radius: 6px; text-decoration: none; font-size: 14px; font-weight: 600;">View Alert Dashboard</a>
      </div>
    </div>
    <div style="padding: 16px 24px; background: #0f1117; text-align: center;">
      <p style="margin: 0; font-size: 12px; color: #4b5563;">InfraPulse AI — Infrastructure Observability Platform</p>
    </div>
  </div>
</body>
</html>
"""


async def send_email(
    to_addresses: List[str],
    subject: str,
    html_body: str,
    smtp_config: Optional[dict] = None,
) -> tuple[bool, str]:
    """Send an email notification."""
    cfg = smtp_config or {}
    host = cfg.get("smtp_host") or settings.SMTP_HOST
    port = cfg.get("smtp_port") or settings.SMTP_PORT
    username = cfg.get("smtp_username") or settings.SMTP_USERNAME
    password = cfg.get("smtp_password") or settings.SMTP_PASSWORD
    use_tls = cfg.get("smtp_tls", settings.SMTP_TLS)
    from_addr = cfg.get("from_address") or settings.SMTP_FROM_ADDRESS
    from_name = cfg.get("from_name") or settings.SMTP_FROM_NAME

    if not host:
        return False, "SMTP host not configured"

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{from_name} <{from_addr}>"
        msg["To"] = ", ".join(to_addresses)
        msg.attach(MIMEText(html_body, "html"))

        smtp = aiosmtplib.SMTP(hostname=host, port=port, use_tls=use_tls)
        await smtp.connect()
        if username and password:
            await smtp.login(username, password)
        await smtp.sendmail(from_addr, to_addresses, msg.as_string())
        await smtp.quit()
        return True, "Email sent successfully"
    except Exception as e:
        logger.error("Email send failed", error=str(e))
        return False, f"Email error: {str(e)}"


async def send_alert_email(alert, server_name: str, org_name: str, to_addresses: List[str], dashboard_url: str, ai_summary: str = None) -> tuple[bool, str]:
    severity_colors = {
        "critical": "#ef4444", "high": "#f97316", "medium": "#f59e0b", "low": "#84cc16", "info": "#3b82f6"
    }
    severity_bgs = {
        "critical": "rgba(239,68,68,0.1)", "high": "rgba(249,115,22,0.1)",
        "medium": "rgba(245,158,11,0.1)", "low": "rgba(132,204,18,0.1)", "info": "rgba(59,130,246,0.1)"
    }
    color = severity_colors.get(alert.severity, "#6b7280")
    bg = severity_bgs.get(alert.severity, "rgba(107,114,128,0.1)")

    template = Template(ALERT_EMAIL_HTML)
    html = template.render(
        title=alert.title,
        severity=alert.severity.upper(),
        severity_color=color,
        severity_bg=bg,
        org_name=org_name,
        server_name=server_name or "N/A",
        rule_type=alert.rule_type or "N/A",
        trigger_value=f"{alert.trigger_value}" if alert.trigger_value is not None else None,
        triggered_at=alert.created_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
        dashboard_url=f"{dashboard_url}/alerts/{alert.id}",
        ai_summary=ai_summary,
    )
    subject = f"[{alert.severity.upper()}] InfraPulse AI Alert: {alert.title}"
    return await send_email(to_addresses, subject, html)
