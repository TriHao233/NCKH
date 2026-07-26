import logging

from core.config import settings
from modules.generation.llm.base import LLMProvider
from modules.generation.llm.deepseek import DeepseekProvider
from modules.generation.llm.gemini import GeminiProvider
from modules.generation.llm.qwen import QwenProvider

logger = logging.getLogger(__name__)


def get_llm_service(provider: str = "qwen") -> LLMProvider:
    provider_code = (provider or settings.model_provider).strip()
    normalized = provider_code.lower()

    if normalized == "gemini":
        return GeminiProvider()
    if normalized == "qwen":
        return QwenProvider()
    if normalized == "deepseek":
        return DeepseekProvider()
    if normalized in {"deepseek-r1", "deepseek-r1:8b"}:
        return DeepseekProvider(model_name=provider_code)
    if normalized.startswith("ollama:"):
        model_name = provider_code.split(":", 1)[1].strip()
        if not model_name:
            raise ValueError("Provider ollama: phai kem ten model")
        return DeepseekProvider(model_name=model_name)

    raise ValueError(f"Provider {provider_code} khong duoc ho tro!")
