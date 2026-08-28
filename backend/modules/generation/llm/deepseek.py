from core.config import settings
from modules.generation.llm.ollama import OllamaProvider


class DeepseekProvider(OllamaProvider):
    def __init__(self, model_name: str | None = None):
        super().__init__(
            model_name or settings.deepseek_model_name,
            provider_label="Deepseek (Ollama)",
            timeout_seconds=settings.deepseek_timeout_seconds,
            num_predict=settings.deepseek_num_predict,
            temperature=settings.deepseek_temperature,
        )
