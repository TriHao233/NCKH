import logging
from collections.abc import Callable

from core.config import settings
from modules.generation.llm.base import LLMProvider
from modules.generation.llm.concurrency import ConcurrencyLimitedProvider
from modules.generation.llm.deepseek import DeepseekProvider
from modules.generation.llm.fallback import FallbackProvider
from modules.generation.llm.gemini import GeminiProvider
from modules.generation.llm.qwen import QwenProvider

logger = logging.getLogger(__name__)

ProviderFactory = Callable[[str], LLMProvider]


def _qwen_factory(_provider_code: str) -> LLMProvider:
    return QwenProvider()


def _gemini_factory(_provider_code: str) -> LLMProvider:
    return GeminiProvider()


def _deepseek_factory(provider_code: str) -> LLMProvider:
    normalized = provider_code.lower()
    model_name = provider_code if normalized in {"deepseek-r1", "deepseek-r1:8b"} else None
    return DeepseekProvider(model_name=model_name)


PROVIDER_REGISTRY: dict[str, ProviderFactory] = {
    "qwen": _qwen_factory,
    "gemini": _gemini_factory,
    "deepseek": _deepseek_factory,
    "deepseek-r1": _deepseek_factory,
    "deepseek-r1:8b": _deepseek_factory,
}


def register_llm_provider(provider_code: str, factory: ProviderFactory) -> None:
    normalized = provider_code.strip().lower()
    if not normalized:
        raise ValueError("provider_code không được để trống")
    PROVIDER_REGISTRY[normalized] = factory


def _get_single_provider(provider: str) -> LLMProvider:
    provider_code = (provider or settings.model_provider).strip()
    normalized = provider_code.lower()

    factory = PROVIDER_REGISTRY.get(normalized)
    if factory:
        return ConcurrencyLimitedProvider(provider_code, factory(provider_code))
    if normalized.startswith("ollama:"):
        model_name = provider_code.split(":", 1)[1].strip()
        if not model_name:
            raise ValueError("Provider ollama: phai kem ten model")
        return ConcurrencyLimitedProvider(provider_code, DeepseekProvider(model_name=model_name))

    raise ValueError(f"Provider {provider_code} khong duoc ho tro!")


def get_llm_service(provider: str = "qwen", fallback_provider: str | None = None) -> LLMProvider:
    primary = _get_single_provider(provider)
    fallback_code = (fallback_provider or "").strip()
    if not fallback_code or fallback_code.lower() == provider.strip().lower():
        return primary
    return FallbackProvider(primary, _get_single_provider(fallback_code))
