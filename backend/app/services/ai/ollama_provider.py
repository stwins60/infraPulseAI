import json
from typing import Tuple
import aiohttp
import structlog
from app.services.ai.base import BaseAIProvider

logger = structlog.get_logger(__name__)


class OllamaProvider(BaseAIProvider):
    DEFAULT_MODEL = "llama3.2"

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def complete(self, prompt: str, model: str) -> Tuple[str, int, int]:
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": model or self.DEFAULT_MODEL,
                    "prompt": f"You are an expert infrastructure operations engineer. Respond with valid JSON only.\n\n{prompt}",
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.1},
                }
                async with session.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    content = data.get("response", "")
                    prompt_eval_count = data.get("prompt_eval_count", 0)
                    eval_count = data.get("eval_count", 0)
                    return content, prompt_eval_count, eval_count
        except Exception as e:
            logger.error("Ollama API error", error=str(e))
            raise
