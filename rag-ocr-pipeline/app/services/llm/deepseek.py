import httpx
import logging

logger = logging.getLogger(__name__)

class DeepseekProvider:
    def __init__(self):
        self.url = "http://host.docker.internal:11434/api/generate"
        self.model_name = "deepseek-r1:8b"

    async def generate_text(self, prompt: str) -> str:
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False
        }
        
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(self.url, json=payload)
                response.raise_for_status()
                result = response.json()
                return result.get("response", "")
                
        except Exception as e:
            error_msg = str(e)
            logger.error(f"--- Deepseek Error: {error_msg}  ---")
            raise Exception(f"Lỗi khi gọi Deepseek (Ollama): {error_msg}")