from abc import ABC, abstractmethod

class LLMProvider(ABC):
    @abstractmethod
    async def generate_text(
        self, prompt: str, response_schema: dict | None = None,
    ) -> str:
        """Hàm trừu tượng để sinh text từ prompt"""
        pass
