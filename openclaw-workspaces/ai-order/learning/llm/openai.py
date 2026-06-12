"""
OpenAI 官方 Provider
使用 openai SDK 调用 OpenAI 官方 API
"""
import os
from .provider import LLMProvider, ChatRequest, ChatResponse

class OpenAIProvider(LLMProvider):
    """使用 OpenAI 官方 API"""
    name = "openai"
    
    def __init__(self, config: dict):
        import openai
        api_key = config.get("api_key", os.getenv("OPENAI_API_KEY"))
        if not api_key:
            raise ValueError("OpenAI API key not configured")
        
        self.client = openai.OpenAI(api_key=api_key)
        self.model = config.get("model", "gpt-4o")
    
    def chat(self, req: ChatRequest) -> ChatResponse:
        """使用 OpenAI 官方 API"""
        resp = self.client.chat.completions.create(
            model=req.model or self.model,
            messages=[
                {"role": "system", "content": req.system},
                {"role": "user", "content": req.user}
            ],
            temperature=req.temperature,
            max_tokens=req.max_tokens
        )
        
        return ChatResponse(
            text=resp.choices[0].message.content,
            provider_name=self.name,
            model=resp.model,
            raw=resp.model_dump()
        )
    
    def is_available(self) -> bool:
        """检查 API key 是否配置"""
        return bool(os.getenv("OPENAI_API_KEY"))