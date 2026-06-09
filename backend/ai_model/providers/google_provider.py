# apps/ai_model/providers/google_provider.py
import json
from typing import AsyncGenerator, Dict, List
from .base import BaseAIProvider

class GoogleAIProvider(BaseAIProvider):
    """Google AI (Gemini) provider"""
    
    API_URL = "https://generativelanguage.googleapis.com/v1beta"
    
    MODELS = {
        "gemini-pro": {"max_tokens": 32768, "supports_vision": False},
        "gemini-pro-vision": {"max_tokens": 32768, "supports_vision": True},
        "gemini-1.5-pro": {"max_tokens": 1048576, "supports_vision": True},
        "gemini-1.5-flash": {"max_tokens": 1048576, "supports_vision": True},
    }
    
    async def stream_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }
        
        # Convert messages to Gemini format
        contents = []
        for msg in messages:
            contents.append({
                "role": "user" if msg["role"] == "user" else "model",
                "parts": [{"text": msg["content"]}]
            })
        
        data = {
            "contents": contents,
            "generationConfig": {
                "temperature": kwargs.get("temperature", 0.7),
                "maxOutputTokens": kwargs.get("max_tokens", 2000),
            }
        }
        
        async with self.session.post(
            f"{self.API_URL}/models/{model}:streamGenerateContent",
            headers=headers,
            json=data
        ) as response:
            response.raise_for_status()
            
            async for line in response.content:
                if line:
                    try:
                        chunk = json.loads(line)
                        if "candidates" in chunk:
                            content = chunk["candidates"][0]["content"]["parts"][0]["text"]
                            yield content
                    except json.JSONDecodeError:
                        continue
    
    def validate_model(self, model_name: str) -> bool:
        return model_name in self.MODELS
    
    def get_model_info(self, model_name: str) -> Dict:
        return self.MODELS.get(model_name, {})
