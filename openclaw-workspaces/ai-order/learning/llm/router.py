"""
LLM Router - 路由 + 回退链
"""
import os
import yaml
from pathlib import Path
from typing import List, Optional
from .provider import LLMProvider, ChatRequest, ChatResponse

class LLMRouter:
    """LLM 路由 + 回退"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self._get_default_config_path()
        self.providers = {}  # name -> provider
        self.default = None
        self.fallbacks = []
        self._load_config()
    
    def _get_default_config_path(self) -> str:
        """获取默认配置文件路径"""
        skill_dir = Path(__file__).parent.parent.parent
        return str(skill_dir / "config" / "llm.yaml")
    
    def _load_config(self):
        """加载配置文件并初始化 providers"""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")
        
        with open(self.config_path) as f:
            config = yaml.safe_load(f)
        
        self.default = config.get("default", "openclaw")
        self.fallbacks = config.get("fallbacks", [])
        
        providers_config = config.get("providers", {})
        for name, cfg in providers_config.items():
            self._create_provider(name, cfg)
    
    def _create_provider(self, name: str, cfg: dict):
        """根据配置创建 provider"""
        ptype = cfg.get("type", "")
        
        if ptype == "openclaw":
            from .openclaw import OpenClawProvider
            self.providers[name] = OpenClawProvider(cfg)
        elif ptype == "openai":
            from .openai import OpenAIProvider
            self.providers[name] = OpenAIProvider(cfg)
        elif ptype == "openai_compat":
            from .openai_compat import OpenAICompatProvider
            self.providers[name] = OpenAICompatProvider(cfg)
        elif ptype == "custom_http":
            from .custom_http import CustomHTTPProvider
            self.providers[name] = CustomHTTPProvider(cfg)
        else:
            raise ValueError(f"未知 provider type: {ptype}")
    
    def chat(self, system: str, user: str, **kwargs) -> ChatResponse:
        """发送聊天请求，带回退链"""
        tried = []
        
        for provider_name in [self.default] + self.fallbacks:
            provider = self.providers.get(provider_name)
            if not provider:
                tried.append(f"{provider_name} (not configured)")
                continue
            
            if not provider.is_available():
                tried.append(f"{provider_name} (not available)")
                continue
            
            try:
                req = ChatRequest(system=system, user=user, **kwargs)
                return provider.chat(req)
            except Exception as e:
                tried.append(f"{provider_name} (error: {e})")
                continue
        
        raise RuntimeError(f"所有 provider 都失败: {tried}")
    
    def list_providers(self) -> List[str]:
        """列出所有已配置的 provider"""
        return list(self.providers.keys())
    
    def get_default(self) -> str:
        """获取默认 provider"""
        return self.default