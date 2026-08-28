from core.config import settings
from modules.generation.llm.ollama import OllamaProvider


class QwenProvider(OllamaProvider):
    def __init__(self):
        super().__init__(settings.qwen_model_name, provider_label="Qwen (Ollama)")
