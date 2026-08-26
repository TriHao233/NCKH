from collections.abc import Callable

from core.config import settings
from modules.generation.llm.base import LLMProvider
from modules.generation.llm.concurrency import ConcurrencyLimitedProvider
from modules.generation.llm.fallback import FallbackProvider
from modules.generation.llm.gemini import GeminiProvider
from modules.generation.llm.model_registry import resolve_direct_model_snapshot
from modules.generation.llm.ollama import OllamaProvider

ProviderFactory = Callable[[str], LLMProvider]
PROVIDER_REGISTRY: dict[str, ProviderFactory] = {}


def register_llm_provider(provider_code: str, factory: ProviderFactory) -> None:
    normalized = provider_code.strip().lower()
    if not normalized:
        raise ValueError("provider_code không được để trống")
    PROVIDER_REGISTRY[normalized] = factory


def _provider_from_snapshot(snapshot: dict) -> LLMProvider:
    runtime = str(snapshot.get("runtime") or "").upper()
    parameters = snapshot.get("parameters") or {}
    if runtime == "OLLAMA":
        provider = OllamaProvider(
            snapshot["model_name"],
            provider_label=snapshot.get("display_name") or "Ollama",
            timeout_seconds=parameters.get("timeout_seconds"),
            num_predict=parameters.get("num_predict"),
            temperature=parameters.get("temperature"),
            url=parameters.get("endpoint"),
        )
        concurrency_code = f"ollama:{snapshot['model_name']}"
    elif runtime == "GEMINI":
        provider = GeminiProvider(
            snapshot["model_name"],
            timeout_seconds=parameters.get("timeout_seconds", 300),
            temperature=parameters.get("temperature", 0),
            max_output_tokens=parameters.get("max_output_tokens", 2048),
        )
        concurrency_code = "gemini"
    else:
        factory = PROVIDER_REGISTRY.get(str(snapshot.get("model_code") or "").lower())
        if not factory:
            raise ValueError(f"Runtime model '{runtime}' chưa được hỗ trợ")
        provider = factory(snapshot["model_code"])
        concurrency_code = snapshot["model_code"]
    provider.runtime_snapshot = dict(snapshot)
    wrapped = ConcurrencyLimitedProvider(concurrency_code, provider)
    wrapped.runtime_snapshot = dict(snapshot)
    return wrapped


def _get_single_provider(provider: str, snapshot: dict | None = None) -> LLMProvider:
    provider_code = (provider or settings.model_provider).strip()
    normalized = provider_code.lower()
    if snapshot is not None:
        return _provider_from_snapshot(snapshot)
    if normalized in PROVIDER_REGISTRY:
        direct = PROVIDER_REGISTRY[normalized](provider_code)
        runtime_snapshot = {
            "requested_code": provider_code,
            "model_code": provider_code,
            "model_name": getattr(direct, "model_name", provider_code),
            "runtime": "REGISTERED",
            "source": "registered",
        }
        direct.runtime_snapshot = runtime_snapshot
        wrapped = ConcurrencyLimitedProvider(provider_code, direct)
        wrapped.runtime_snapshot = runtime_snapshot
        return wrapped
    return _provider_from_snapshot(resolve_direct_model_snapshot(provider_code))


def get_llm_service(
    provider: str = "qwen",
    fallback_provider: str | None = None,
    *,
    model_snapshot: dict | None = None,
    fallback_model_snapshot: dict | None = None,
) -> LLMProvider:
    primary = _get_single_provider(provider, model_snapshot)
    fallback_code = (fallback_provider or "").strip()
    if not fallback_code or fallback_code.lower() == provider.strip().lower():
        return primary
    return FallbackProvider(
        primary,
        _get_single_provider(fallback_code, fallback_model_snapshot),
    )


def get_llm_execution_snapshot(provider: LLMProvider) -> dict:
    if isinstance(provider, FallbackProvider):
        return provider.execution_snapshot()
    snapshot = dict(getattr(provider, "runtime_snapshot", {}) or {})
    return {"fallback_used": False, "used_model": snapshot, "primary_model": snapshot}


def reset_llm_execution_tracking(provider: LLMProvider) -> None:
    if isinstance(provider, FallbackProvider):
        provider.reset_execution_tracking()
