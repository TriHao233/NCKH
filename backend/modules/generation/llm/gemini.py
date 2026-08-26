import asyncio
import logging
import re

from google import genai
from google.genai import types

from core.config import settings
from modules.generation.llm.base import LLMProvider

logger = logging.getLogger(__name__)

class GeminiProvider(LLMProvider):
    def __init__(
        self,
        model_name: str | None = None,
        *,
        timeout_seconds: float = 300,
        temperature: float = 0,
        max_output_tokens: int = 2048,
    ):
        self.client = genai.Client(api_key=settings.gemini_api_key)

        self.model_name = (model_name or settings.gemini_model_name).replace("models/", "")
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens

    async def generate_text(self, prompt: str) -> str:
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self.client.models.generate_content,
                    model=self.model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=self.temperature,
                        max_output_tokens=self.max_output_tokens,
                    ),
                ),
                timeout=self.timeout_seconds,
            )

            if not response.text:
                raise Exception("Gemini trả về kết quả rỗng")

            text = response.text
            clean_text = re.sub(r'```json|```', '', text).strip()

            return clean_text

        except Exception as exc:
            logger.exception("Gemini request failed: %s", exc)
            raise RuntimeError(f"Lỗi khi gọi Gemini API: {exc}") from exc
