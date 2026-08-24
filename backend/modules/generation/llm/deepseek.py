import httpx
import logging

from core.config import settings

logger = logging.getLogger(__name__)

class DeepseekProvider:
    def __init__(self, model_name: str | None = None):
        self.url = settings.ollama_generate_url
        self.model_name = (model_name or settings.deepseek_model_name).strip()

    async def generate_text(self, prompt: str) -> str:
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": settings.deepseek_temperature,
                "num_predict": settings.deepseek_num_predict,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=settings.deepseek_timeout_seconds) as client:
                response = await client.post(self.url, json=payload)
                response.raise_for_status()
                result = response.json()
                return result.get("response", "")

        except Exception as e:
            error_msg = str(e)
            if "All connection attempts failed" in error_msg:
                error_msg = "Không thể kết nối đến máy chủ AI (Tất cả kết nối đều thất bại)"
            elif "timeout" in error_msg.lower():
                error_msg = "Máy chủ AI phản hồi quá lâu (Timeout)"
            logger.error(f"--- Deepseek Error: {error_msg}  ---")
            raise Exception(f"Lỗi khi gọi Deepseek (Ollama): {error_msg}")
