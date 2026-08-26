import asyncio
import logging
import re

from google import genai

from core.config import settings
from modules.generation.llm.base import LLMProvider

logger = logging.getLogger(__name__)

class GeminiProvider(LLMProvider):
    def __init__(self):
        self.client = genai.Client(api_key=settings.gemini_api_key)

        self.model_name = settings.gemini_model_name.replace("models/", "")

    async def generate_text(self, prompt: str) -> str:
        try:
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model_name,
                contents=prompt,
            )

            if not response.text:
                raise Exception("Gemini trả về kết quả rỗng")

            text = response.text
            clean_text = re.sub(r'```json|```', '', text).strip()

            return clean_text

        except Exception as exc:
            logger.exception("Gemini request failed: %s", exc)
            raise RuntimeError(f"Lỗi khi gọi Gemini API: {exc}") from exc
