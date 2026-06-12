"""
OpenAI 兼容 API Provider
支持所有兼容 OpenAI Chat Completions 接口的服务
- MiniMax
- DeepSeek
- 通义千问 (Qwen)
- 月之暗面 Kimi
- 智谱 GLM
- 自部署 vLLM / Ollama
等
"""
import os
from .provider import LLMProvider, ChatRequest, ChatResponse

class OpenAICompatProvider(LLMProvider):
    """所有兼容 OpenAI Chat Completions 接口的服务"""
    name = "openai_compat"  # 默认 name，会被 config.alias 覆盖
    
    def __init__(self, config: dict):
        import openai
        
        self.base_url = config.get("base_url", "")
        api_key = config.get("api_key", os.getenv("MINIMAX_API_KEY"))
        
        if not self.base_url:
            raise ValueError("OpenAI 兼容模式需要 base_url")
        if not api_key:
            raise ValueError("API key not configured")
        
        self.client = openai.OpenAI(api_key=api_key, base_url=self.base_url)
        self.model = config.get("model", "gpt-4o")
        # 自定义 provider 名称（如 "MiniMax", "DeepSeek" 等）
        self.name = config.get("alias", self.base_url)
    
    def chat(self, req: ChatRequest) -> ChatResponse:
        """使用 OpenAI 兼容 API"""
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
        """检查 API key 和 base_url 是否配置"""
        return bool(self.base_url and self.client.api_key)