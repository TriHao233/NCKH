from abc import ABC, abstractmethod
import json
from typing import Any

class LLMProvider(ABC):
    @abstractmethod
    async def generate_text(self, prompt: str) -> str:
        """Hàm trừu tượng để sinh text từ prompt"""
        pass

    async def generate_chat(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_schema: dict[str, Any] | None = None,
    ) -> str:
        """Structured chat fallback for providers without a native chat API."""
        schema_block = (
            "\n\nOUTPUT JSON SCHEMA:\n" + json.dumps(output_schema, ensure_ascii=False)
            if output_schema
            else ""
        )
        prompt = f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_prompt}{schema_block}"
        return await self.generate_text(prompt)
