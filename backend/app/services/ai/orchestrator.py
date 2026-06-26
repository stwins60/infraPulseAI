import json
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.models.organization import Organization
from app.models.alert import Alert
from app.models.incident import Incident
from app.models.server import Server
from app.models.metric import Metric
from app.models.log_entry import LogEntry
from app.models.ai_analysis import AIAnalysis
from app.services.ai.base import BaseAIProvider
from app.services.ai.groq_provider import GroqProvider
from app.services.ai.openai_provider import OpenAIProvider
from app.services.ai.ollama_provider import OllamaProvider
from app.services.ai.prompts import (
    ANALYSIS_PROMPT_TEMPLATE, SERVER_HEALTH_PROMPT, redact_sensitive_data
)
from app.services.encryption_service import decrypt_dict

logger = structlog.get_logger(__name__)


class AIOrchestrator:
    def __init__(self, org: Organization, db: AsyncSession):
        self.org = org
        self.db = db

    def _get_provider(self) -> tuple[BaseAIProvider, str, str]:
        """Get configured AI provider for the organization."""
        config = self.org.ai_provider_config or {}

        # Decrypt sensitive config
        encrypted = config.get("_encrypted_sensitive")
        sensitive = {}
        if encrypted:
            try:
                sensitive = decrypt_dict(encrypted)
            except Exception:
                pass

        provider_name = config.get("provider", "groq")
        model = config.get("model", "")

        if provider_name == "openai":
            api_key = sensitive.get("openai_api_key") or settings.OPENAI_API_KEY
            if not api_key:
                raise ValueError("OpenAI API key not configured")
            return OpenAIProvider(api_key), "openai", model or "gpt-4o-mini"
        elif provider_name == "ollama":
            ollama_url = config.get("ollama_url") or settings.OLLAMA_BASE_URL
            return OllamaProvider(ollama_url), "ollama", model or "llama3.2"
        else:  # groq (default)
            api_key = sensitive.get("groq_api_key") or settings.GROQ_API_KEY
            if not api_key:
                raise ValueError("Groq API key not configured")
            return GroqProvider(api_key), "groq", model or "llama-3.3-70b-versatile"

    async def _get_recent_metrics(self, server_id: UUID, minutes: int = 15) -> str:
        since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        result = await self.db.execute(
            select(Metric)
            .where(
                Metric.server_id == server_id,
                Metric.timestamp >= since,
                Metric.metric_name.in_(["cpu_percent", "memory_percent", "disk_percent", "load_avg_1m", "network_bytes_recv", "network_bytes_sent"])
            )
            .order_by(Metric.timestamp.desc())
            .limit(50)
        )
        metrics = result.scalars().all()
        if not metrics:
            return "No recent metrics available"
        lines = [f"- {m.metric_name}: {m.value}{m.unit or ''} at {m.timestamp.strftime('%H:%M:%S')}" for m in metrics]
        return "\n".join(lines[:30])

    async def _get_recent_logs(self, server_id: UUID, minutes: int = 30, limit: int = 50) -> str:
        since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        result = await self.db.execute(
            select(LogEntry)
            .where(
                LogEntry.server_id == server_id,
                LogEntry.timestamp >= since,
                LogEntry.severity.in_(["error", "critical", "warning"])
            )
            .order_by(LogEntry.timestamp.desc())
            .limit(limit)
        )
        logs = result.scalars().all()
        if not logs:
            return "No recent error/warning logs"
        lines = [f"[{log.severity.upper()}] {log.timestamp.strftime('%H:%M:%S')} {log.service or 'system'}: {log.message[:200]}" for log in logs]
        return redact_sensitive_data("\n".join(lines))

    async def analyze_alert(self, alert: Alert, requested_by_id=None) -> AIAnalysis:
        try:
            provider, provider_name, model = self._get_provider()
        except ValueError as e:
            # Return a failed analysis if AI not configured
            analysis = AIAnalysis(
                organization_id=self.org.id,
                alert_id=alert.id,
                analysis_type="alert_analysis",
                provider="none",
                model="none",
                result={"summary": f"AI analysis unavailable: {str(e)}", "severity_assessment": alert.severity},
                status="failed",
                error_message=str(e),
                requested_by_id=requested_by_id,
            )
            self.db.add(analysis)
            await self.db.commit()
            return analysis

        # Build context
        metrics_text = ""
        logs_text = ""
        server_info = ""

        if alert.server_id:
            server = await self.db.get(Server, alert.server_id)
            if server:
                server_info = f"Hostname: {server.hostname}, OS: {server.os_type} {server.os_version}, CPUs: {server.cpu_count}"
                metrics_text = await self._get_recent_metrics(alert.server_id)
                logs_text = await self._get_recent_logs(alert.server_id)

        alert_details = f"""
Title: {alert.title}
Description: {alert.description or 'N/A'}
Severity: {alert.severity}
Rule Type: {alert.rule_type or 'N/A'}
Trigger Value: {alert.trigger_value}
Threshold: {alert.threshold_value}
Triggered at: {alert.created_at.isoformat()}
"""

        prompt = ANALYSIS_PROMPT_TEMPLATE.format(
            context=f"Organization: {self.org.name}\nServer: {server_info}",
            alert_details=alert_details,
            metrics=metrics_text,
            logs=logs_text,
            previous_incidents="No previous incidents found",
        )

        try:
            result, raw_response, prompt_tokens, completion_tokens = await provider.analyze(prompt, model)
        except Exception as e:
            logger.error("AI analysis failed", error=str(e), alert_id=str(alert.id))
            result = {"summary": f"AI analysis failed: {str(e)}", "severity_assessment": alert.severity}
            raw_response = ""
            prompt_tokens = 0
            completion_tokens = 0

        analysis = AIAnalysis(
            organization_id=self.org.id,
            alert_id=alert.id,
            server_id=alert.server_id,
            analysis_type="alert_analysis",
            provider=provider_name,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            result=result,
            raw_response=raw_response[:5000] if raw_response else None,
            evidence_used=[
                {"type": "metrics", "count": metrics_text.count("\n") + 1},
                {"type": "logs", "count": logs_text.count("\n") + 1},
            ],
            status="completed",
            requested_by_id=requested_by_id,
        )
        self.db.add(analysis)
        alert.ai_analyzed = True
        await self.db.commit()
        await self.db.refresh(analysis)
        return analysis

    async def analyze_server(self, server: Server, requested_by_id=None) -> AIAnalysis:
        try:
            provider, provider_name, model = self._get_provider()
        except ValueError as e:
            analysis = AIAnalysis(
                organization_id=self.org.id,
                server_id=server.id,
                analysis_type="server_health",
                provider="none",
                model="none",
                result={"summary": f"AI analysis unavailable: {str(e)}"},
                status="failed",
                error_message=str(e),
                requested_by_id=requested_by_id,
            )
            self.db.add(analysis)
            await self.db.commit()
            return analysis

        metrics_text = await self._get_recent_metrics(server.id, minutes=60)
        logs_text = await self._get_recent_logs(server.id, minutes=60)

        # Recent alerts
        from app.models.alert import Alert
        alerts_result = await self.db.execute(
            select(Alert)
            .where(Alert.server_id == server.id, Alert.status == "open")
            .limit(10)
        )
        alerts = alerts_result.scalars().all()
        alerts_text = "\n".join([f"- [{a.severity.upper()}] {a.title}" for a in alerts]) or "No open alerts"

        server_info = f"""
Hostname: {server.hostname}
OS: {server.os_type} {server.os_version}
Kernel: {server.kernel_version}
CPU Count: {server.cpu_count}
Memory Total: {server.memory_total_bytes // (1024**3) if server.memory_total_bytes else 'unknown'} GB
Environment: {server.environment}
Status: {server.status}
Last seen: {server.last_seen_at.isoformat() if server.last_seen_at else 'unknown'}
"""

        prompt = SERVER_HEALTH_PROMPT.format(
            server_info=server_info,
            metrics=metrics_text,
            alerts=alerts_text,
            logs=logs_text,
        )

        try:
            result, raw_response, prompt_tokens, completion_tokens = await provider.analyze(prompt, model)
        except Exception as e:
            result = {"summary": f"Analysis failed: {str(e)}", "health_score": server.health_score or 0}
            raw_response = ""
            prompt_tokens = 0
            completion_tokens = 0

        analysis = AIAnalysis(
            organization_id=self.org.id,
            server_id=server.id,
            analysis_type="server_health",
            provider=provider_name,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            result=result,
            raw_response=raw_response[:5000] if raw_response else None,
            status="completed",
            requested_by_id=requested_by_id,
        )
        self.db.add(analysis)
        await self.db.commit()
        await self.db.refresh(analysis)
        return analysis

    async def analyze_incident(self, incident: Incident, requested_by_id=None) -> AIAnalysis:
        try:
            provider, provider_name, model = self._get_provider()
        except ValueError as e:
            analysis = AIAnalysis(
                organization_id=self.org.id,
                incident_id=incident.id,
                analysis_type="incident_analysis",
                provider="none",
                model="none",
                result={"summary": f"AI analysis unavailable: {str(e)}"},
                status="failed",
                error_message=str(e),
                requested_by_id=requested_by_id,
            )
            self.db.add(analysis)
            await self.db.commit()
            return analysis

        incident_info = f"""
Title: {incident.title}
Description: {incident.description or 'N/A'}
Severity: {incident.severity}
Status: {incident.status}
Created: {incident.created_at.isoformat()}
Timeline events: {len(incident.timeline or [])}
"""

        prompt = f"""
Analyze this infrastructure incident and provide remediation guidance.

INCIDENT DETAILS:
{incident_info}

Respond with JSON:
{{
  "summary": "Incident summary",
  "severity_assessment": "Critical|High|Medium|Low",
  "likely_root_causes": [{{"cause": "", "confidence": 0.0, "evidence": []}}],
  "recommended_actions": [{{"action": "", "priority": "immediate", "rationale": ""}}],
  "safe_commands": [],
  "risk_notes": [],
  "executive_summary": "One paragraph for non-technical stakeholders",
  "estimated_resolution_time": "e.g., 30 minutes",
  "analysis_confidence": 0.8
}}
"""
        try:
            result, raw_response, prompt_tokens, completion_tokens = await provider.analyze(prompt, model)
        except Exception as e:
            result = {"summary": f"Analysis failed: {str(e)}"}
            raw_response = ""
            prompt_tokens = 0
            completion_tokens = 0

        analysis = AIAnalysis(
            organization_id=self.org.id,
            incident_id=incident.id,
            analysis_type="incident_analysis",
            provider=provider_name,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            result=result,
            raw_response=raw_response[:5000] if raw_response else None,
            status="completed",
            requested_by_id=requested_by_id,
        )
        self.db.add(analysis)
        await self.db.commit()
        await self.db.refresh(analysis)
        return analysis
