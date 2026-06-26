import json
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Tuple
import structlog

logger = structlog.get_logger(__name__)


class BaseAIProvider(ABC):
    """Abstract base class for AI providers."""

    @abstractmethod
    async def complete(self, prompt: str, model: str) -> Tuple[str, int, int]:
        """
        Send a prompt and return (response_text, prompt_tokens, completion_tokens).
        """
        pass

    async def analyze(self, prompt: str, model: str) -> Dict[str, Any]:
        """Run analysis and parse JSON response."""
        raw_response, prompt_tokens, completion_tokens = await self.complete(prompt, model)

        # Extract JSON from response
        try:
            # Try to find JSON block
            import re
            json_match = re.search(r'\{.*\}', raw_response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                result = json.loads(raw_response)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("Failed to parse AI JSON response", error=str(e))
            result = {
                "summary": raw_response[:500] if raw_response else "Analysis failed",
                "severity_assessment": "Unknown",
                "likely_root_causes": [],
                "recommended_actions": [],
                "safe_commands": [],
                "risk_notes": ["AI response could not be parsed as structured JSON"],
                "questions_for_operator": [],
                "similar_past_incidents": [],
                "analysis_confidence": 0.1,
            }

        return result, raw_response, prompt_tokens, completion_tokens
