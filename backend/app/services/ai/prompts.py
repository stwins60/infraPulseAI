import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from uuid import UUID

import structlog

from app.config import settings

logger = structlog.get_logger(__name__)


ANALYSIS_PROMPT_TEMPLATE = """
You are an expert infrastructure operations engineer and AI assistant for InfraPulse AI.
Analyze the following infrastructure alert/incident and provide a structured assessment.

IMPORTANT RULES:
- Distinguish facts from hypotheses clearly
- Never claim certainty without evidence
- Cite the specific logs and metrics used for conclusions
- Do not expose secrets, passwords, or API tokens in your response
- Mark any suggested shell commands as either SAFE or POTENTIALLY_DESTRUCTIVE
- Do not automatically execute any commands

INFRASTRUCTURE CONTEXT:
{context}

ALERT DETAILS:
{alert_details}

RECENT METRICS (5 minutes before alert):
{metrics}

RELEVANT LOGS (15 minutes around alert time):
{logs}

PREVIOUS INCIDENTS:
{previous_incidents}

Please respond with a JSON object following this exact schema:
{{
  "summary": "Short 1-2 sentence explanation of what happened",
  "severity_assessment": "Critical|High|Medium|Low|Info",
  "likely_root_causes": [
    {{
      "cause": "Description of cause",
      "confidence": 0.0-1.0,
      "evidence": ["evidence item 1", "evidence item 2"]
    }}
  ],
  "affected_components": ["component1", "component2"],
  "recommended_actions": [
    {{
      "action": "Description of action",
      "priority": "immediate|short_term|long_term",
      "rationale": "Why this action"
    }}
  ],
  "safe_commands": [
    {{
      "command": "the command",
      "purpose": "what it does",
      "risk_level": "safe|caution|destructive"
    }}
  ],
  "risk_notes": ["risk note 1"],
  "questions_for_operator": ["question 1"],
  "similar_past_incidents": [],
  "analysis_confidence": 0.0-1.0
}}
"""

SERVER_HEALTH_PROMPT = """
You are an expert infrastructure operations engineer.
Analyze the health of the following server and provide actionable recommendations.

SERVER INFORMATION:
{server_info}

CURRENT METRICS:
{metrics}

RECENT ALERTS (last 24h):
{alerts}

RECENT ERROR LOGS:
{logs}

Respond with a JSON object:
{{
  "summary": "Overall health summary",
  "health_score": 0-100,
  "status": "healthy|warning|critical|degraded",
  "issues": [
    {{
      "issue": "Description",
      "severity": "critical|high|medium|low",
      "evidence": ["evidence"],
      "recommendation": "What to do"
    }}
  ],
  "performance_observations": ["observation"],
  "recommended_actions": ["action"],
  "maintenance_suggestions": ["suggestion"]
}}
"""


def redact_sensitive_data(text: str) -> str:
    """Remove potential secrets from text before sending to AI."""
    import re
    patterns = [
        (r'password["\s:=]+[^\s,"\n}{]+', 'password=[REDACTED]'),
        (r'passwd["\s:=]+[^\s,"\n}{]+', 'passwd=[REDACTED]'),
        (r'secret["\s:=]+[^\s,"\n}{]+', 'secret=[REDACTED]'),
        (r'api_key["\s:=]+[^\s,"\n}{]+', 'api_key=[REDACTED]'),
        (r'token["\s:=]+[^\s,"\n}{]+', 'token=[REDACTED]'),
        (r'-----BEGIN [A-Z ]+-----.*?-----END [A-Z ]+-----', '[REDACTED_KEY]'),
        (r'[A-Za-z0-9+/]{40,}={0,2}', lambda m: '[REDACTED_BASE64]' if len(m.group()) > 50 else m.group()),
    ]
    for pattern, replacement in patterns:
        if callable(replacement):
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE | re.DOTALL)
        else:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE | re.DOTALL)
    return text
