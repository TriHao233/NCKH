import logging
import re

import httpx

from core.config import settings
from modules.generation.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """Shared, configurable Ollama transport for local LLM providers."""

    def __init__(
        self,
        model_name: str,
        *,
        provider_label: str = "Ollama",
        timeout_seconds: float | None = None,
        num_predict: int | None = None,
        temperature: float | None = None,
    ):
        self.url = settings.ollama_generate_url
        self.model_name = model_name.strip()
        self.provider_label = provider_label
        self.timeout_seconds = timeout_seconds or settings.ollama_timeout_seconds
        self.num_predict = num_predict if num_predict is not None else settings.ollama_num_predict
        self.temperature = temperature if temperature is not None else settings.ollama_temperature

    async def generate_text(self, prompt: str) -> str:
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": self.temperature,
                "num_predict": self.num_predict,
            },
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(self.url, json=payload)
                response.raise_for_status()
            text = response.json().get("response", "")
            cleaned = re.sub(r"```json|```", "", text).strip()
            if not cleaned:
                raise RuntimeError(f"{self.provider_label} returned an empty response")
            return cleaned
        except Exception as exc:
            message = str(exc)
            if "All connection attempts failed" in message:
                message = "Không thể kết nối đến máy chủ AI"
            elif "timeout" in message.lower():
                message = "Máy chủ AI phản hồi quá lâu (Timeout)"
            logger.exception("%s request failed: %s", self.provider_label, message)
            raise RuntimeError(f"Lỗi khi gọi {self.provider_label}: {message}") from exc
