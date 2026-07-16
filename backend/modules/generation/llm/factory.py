import logging

from modules.generation.llm.base import LLMProvider
from modules.generation.llm.gemini import GeminiProvider
from modules.generation.llm.qwen import QwenProvider
from modules.generation.llm.deepseek import DeepseekProvider

logger = logging.getLogger(__name__)

def get_llm_service(provider: str = "qwen") -> LLMProvider:
    """Factory pattern để khởi tạo LLM dựa trên request của người dùng."""
    provider = provider.lower().strip()
    if provider == "gemini":
        return GeminiProvider()
    elif provider == "qwen":
        return QwenProvider()
    elif provider == "deepseek":
        return DeepseekProvider()
    else:
        raise ValueError(f"Provider {provider} không được hỗ trợ!")
