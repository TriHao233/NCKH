import httpx
import json
import re
from modules.generation.llm.base import LLMProvider

import os

class QwenProvider(LLMProvider):
    def __init__(self):
        # Sử dụng host.docker.internal để backend trong Docker gọi được Ollama cài trên máy host (Windows)
        self.url = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434/api/generate")
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
                if "All connection attempts failed" in error_msg:
                    error_msg = "Không thể kết nối đến máy chủ AI (Tất cả kết nối đều thất bại)"
                elif "timeout" in error_msg.lower():
                    error_msg = "Máy chủ AI phản hồi quá lâu (Timeout)"
                print(f"--- Qwen Error: {error_msg} ---")
                traceback.print_exc()
                raise Exception(f"Lỗi khi gọi Qwen (Ollama): {error_msg}")
