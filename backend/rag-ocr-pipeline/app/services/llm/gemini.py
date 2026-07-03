from google import genai
import re
from app.services.llm.base import LLMProvider
from app.core.config import settings

class GeminiProvider(LLMProvider):
    def __init__(self):
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        
        self.model_name = settings.DEFAULT_MODEL.replace("models/", "")

    async def generate_text(self, prompt: str) -> str:
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            
            if not response.text:
                raise Exception("Gemini trả về kết quả rỗng")
            
            text = response.text
            clean_text = re.sub(r'```json|```', '', text).strip()
            
            return clean_text
            
        except Exception as e:
            print(f"--- Gemini Error Detail: {str(e)} ---")
            raise Exception(f"Lỗi khi gọi Gemini API (SDK mới): {str(e)}")