"""
LLM Provider 接口定义
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass
class ChatRequest:
    """LLM 聊天请求"""
    system: str
    user: str
    model: Optional[str] = None
    temperature: float = 0.1
    max_tokens: int = 4000

@dataclass
class ChatResponse:
    """LLM 聊天响应"""
    text: str
    provider_name: str
    model: str
    raw: Dict[str, Any]  # 原始响应，调试用

class LLMProvider(ABC):
    """LLM Provider 抽象接口"""
    name: str = ""  # "openclaw", "openai", "minimax" etc.
    
    @abstractmethod
    def chat(self, req: ChatRequest) -> ChatResponse:
        """发送聊天请求，返回响应"""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """检查 provider 是否可用（探活）"""
        pass