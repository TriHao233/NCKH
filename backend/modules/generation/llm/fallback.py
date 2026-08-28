import logging

from modules.generation.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class FallbackProvider(LLMProvider):
    def __init__(self, primary: LLMProvider, fallback: LLMProvider):
        self.primary = primary
        self.fallback = fallback
        self.model_name = getattr(primary, "model_name", None)
        self.fallback_model_name = getattr(fallback, "model_name", None)
        self.last_used = "primary"
        self.primary_error: str | None = None
        self.fallback_was_used = False

    async def generate_text(self, prompt: str) -> str:
        try:
            self.last_used = "primary"
            self.primary_error = None
            return await self.primary.generate_text(prompt)
        except (RuntimeError, TimeoutError) as exc:
            self.last_used = "fallback"
            self.primary_error = str(exc)
            self.fallback_was_used = True
            logger.warning(
                "Primary LLM failed; using fallback model %s",
                self.fallback_model_name,
                exc_info=True,
            )
            return await self.fallback.generate_text(prompt)

    def execution_snapshot(self) -> dict:
        primary = dict(getattr(self.primary, "runtime_snapshot", {}) or {})
        fallback = dict(getattr(self.fallback, "runtime_snapshot", {}) or {})
        return {
            "fallback_used": self.fallback_was_used,
            "used_model": fallback if self.last_used == "fallback" else primary,
            "primary_model": primary,
            "fallback_model": fallback,
            "primary_error": self.primary_error,
        }

    def reset_execution_tracking(self) -> None:
        self.last_used = "primary"
        self.primary_error = None
        self.fallback_was_used = False
