import asyncio
import logging
import re
import warnings

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
        max_output_tokens: int | None = None,
    ):
        self.client = genai.Client(api_key=settings.gemini_api_key)

        self.model_name = (model_name or settings.gemini_model_name).replace("models/", "")
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens or settings.gemini_max_output_tokens

    @staticmethod
    def _clean_text(text: str) -> str:
        return re.sub(r'```json|```', '', text).strip()

    @staticmethod
    def _extract_interaction_text(response) -> str:
        text = getattr(response, "output_text", None)
        if text:
            return text
        chunks = []
        for step in getattr(response, "steps", []) or []:
            for content in getattr(step, "content", []) or []:
                content_text = getattr(content, "text", None)
                if content_text:
                    chunks.append(content_text)
        return "\n".join(chunks)

    def _generate_with_interactions(self, prompt: str) -> str:
        generation_config = {"max_output_tokens": self.max_output_tokens}
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            response = self.client.interactions.create(
                model=self.model_name,
                input=prompt,
                generation_config=generation_config,
            )
        return self._extract_interaction_text(response)

    def _generate_with_generate_content(self, prompt: str) -> str:
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=self.temperature,
                max_output_tokens=self.max_output_tokens,
            ),
        )
        return response.text or ""

    def _generate_sync(self, prompt: str) -> str:
        if self.model_name.startswith("gemini-3"):
            return self._generate_with_interactions(prompt)
        return self._generate_with_generate_content(prompt)

    async def generate_text(self, prompt: str) -> str:
        try:
            text = await asyncio.wait_for(
                asyncio.to_thread(self._generate_sync, prompt),
                timeout=self.timeout_seconds,
            )

            if not text:
                raise Exception("Gemini trả về kết quả rỗng")

            return self._clean_text(text)

        except Exception as exc:
            logger.exception("Gemini request failed: %s", exc)
            raise RuntimeError(f"Lỗi khi gọi Gemini API: {exc}") from exc
