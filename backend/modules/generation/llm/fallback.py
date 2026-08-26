import logging

from modules.generation.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class FallbackProvider(LLMProvider):
    def __init__(self, primary: LLMProvider, fallback: LLMProvider):
        self.primary = primary
        self.fallback = fallback
        self.model_name = getattr(primary, "model_name", None)
        self.fallback_model_name = getattr(fallback, "model_name", None)

    async def generate_text(self, prompt: str) -> str:
        try:
            return await self.primary.generate_text(prompt)
        except RuntimeError:
            logger.warning(
                "Primary LLM failed; using fallback model %s",
                self.fallback_model_name,
                exc_info=True,
            )
            return await self.fallback.generate_text(prompt)
