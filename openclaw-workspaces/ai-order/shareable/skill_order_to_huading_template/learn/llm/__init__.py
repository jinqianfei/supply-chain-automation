"""
LLM Provider 模块 - 多 provider 支持
支持：
- OpenClaw 平台内嵌模型（默认）
- OpenAI 官方 API
- OpenAI 兼容 API（MiniMax、DeepSeek、Qwen、Kimi 等）
- 通用 HTTP Provider（Anthropic Claude 等非 OpenAI 协议）
"""
from .provider import LLMProvider, ChatRequest, ChatResponse
from .router import LLMRouter
from .openclaw import OpenClawProvider
from .openai import OpenAIProvider
from .openai_compat import OpenAICompatProvider
from .custom_http import CustomHTTPProvider

__all__ = [
    "LLMProvider",
    "ChatRequest",
    "ChatResponse",
    "LLMRouter",
    "OpenClawProvider",
    "OpenAIProvider",
    "OpenAICompatProvider",
    "CustomHTTPProvider",
]