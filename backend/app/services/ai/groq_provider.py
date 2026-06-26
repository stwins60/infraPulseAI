from typing import Tuple
import structlog
from app.services.ai.base import BaseAIProvider

logger = structlog.get_logger(__name__)


class GroqProvider(BaseAIProvider):
    DEFAULT_MODEL = "llama-3.3-70b-versatile"

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def complete(self, prompt: str, model: str) -> Tuple[str, int, int]:
        try:
            from groq import AsyncGroq
            client = AsyncGroq(api_key=self.api_key)
            response = await client.chat.completions.create(
                model=model or self.DEFAULT_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert infrastructure operations engineer. Respond with valid JSON only.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=4096,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            prompt_tokens = response.usage.prompt_tokens if response.usage else 0
            completion_tokens = response.usage.completion_tokens if response.usage else 0
            return content, prompt_tokens, completion_tokens
        except Exception as e:
            logger.error("Groq API error", error=str(e))
            raise
