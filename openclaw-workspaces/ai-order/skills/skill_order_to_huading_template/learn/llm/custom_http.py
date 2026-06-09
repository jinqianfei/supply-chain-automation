"""
通用 HTTP Provider（非 OpenAI 协议）
用于不支持 OpenAI 协议的服务，如 Anthropic Claude、Google Gemini 等
用户自己定义 request/response 解析规则
"""
import os
import requests
from .provider import LLMProvider, ChatRequest, ChatResponse

class CustomHTTPProvider(LLMProvider):
    """通用 HTTP POST 调用，用户自己定义 request/response"""
    name = "custom_http"
    
    def __init__(self, config: dict):
        self.url = config.get("url", "")
        self.headers = config.get("headers", {})
        self.extra_body = config.get("extra_body", {})
        self.text_path = config.get("text_path", "content.0.text")
        self.timeout = config.get("timeout", 60)
        self.name = config.get("alias", self.url)  # 自定义名称
        
        # 如果 headers 中的 value 是 ${ENV_VAR}，替换为环境变量
        self._resolve_env_vars()
    
    def _resolve_env_vars(self):
        """解析环境变量占位符"""
        for key, value in list(self.headers.items()):
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                env_name = value[2:-1]
                self.headers[key] = os.getenv(env_name, value)
    
    def chat(self, req: ChatRequest) -> ChatResponse:
        """使用通用 HTTP API"""
        resp = requests.post(
            self.url,
            json={
                "system": req.system,
                "user": req.user,
                **self.extra_body
            },
            headers=self.headers,
            timeout=self.timeout
        )
        
        data = resp.json()
        text = self._extract_text(data)
        model = data.get("model", "unknown")
        
        return ChatResponse(
            text=text,
            provider_name=self.name,
            model=model,
            raw=data
        )
    
    def _extract_text(self, data: dict) -> str:
        """从响应 JSON 中提取文本"""
        keys = self.text_path.split(".")
        value = data
        for key in keys:
            if not value:
                return ""
            if key.isdigit():
                value = value[int(key)]
            else:
                value = value.get(key, "")
        return str(value) if value else ""
    
    def is_available(self) -> bool:
        """检查 URL 是否配置"""
        return bool(self.url)