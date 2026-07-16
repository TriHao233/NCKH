import httpx
import json
import re
from modules.generation.llm.base import LLMProvider

class QwenProvider(LLMProvider):
    def __init__(self):
        # Địa chỉ API mặc định của Ollama
        self.url = "http://localhost:11434/api/generate"
        # Đảm bảo tên này khớp với cột NAME trong lệnh 'ollama list'
        self.model_name = "qwen2.5:7b"

    async def generate_text(self, prompt: str) -> str:
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "format": "json"
        }

        async with httpx.AsyncClient(timeout=300.0) as client:
            try:
                response = await client.post(self.url, json=payload)
                response.raise_for_status()

                result = response.json()
                text = result.get("response", "")

                clean_text = re.sub(r'```json|```', '', text).strip()
                return clean_text

            except Exception as e:
                import traceback
                error_msg = f"{type(e).__name__}: {str(e)}"
                print(f"--- Qwen Error: {error_msg} ---")
                traceback.print_exc()
                raise Exception(f"Lỗi khi gọi Qwen (Ollama): {error_msg}")
