"""
OpenClaw 平台内嵌模型 Provider
通过 openclaw infer model run 调用平台当前 agent 的模型
"""
import subprocess
import json
import shutil
from .provider import LLMProvider, ChatRequest, ChatResponse

class OpenClawProvider(LLMProvider):
    """通过 openclaw infer model run 调用平台模型"""
    name = "openclaw"
    
    def __init__(self, config: dict = None):
        """初始化（config 可为空）"""
        self.config = config or {}
    
    def chat(self, req: ChatRequest) -> ChatResponse:
        """使用 OpenClaw 平台模型"""
        full_prompt = f"{req.system}\n\n{req.user}"
        
        try:
            result = subprocess.run(
                ["openclaw", "infer", "model", "run",
                 "--prompt", full_prompt, "--json"],
                capture_output=True, text=True, timeout=60
            )
            
            # 解析 JSON 响应
            data = json.loads(result.stdout)
            
            if not data.get("ok"):
                raise RuntimeError(f"OpenClaw inference failed: {data.get('error', 'unknown')}")
            
            outputs = data.get("outputs", [])
            if not outputs:
                raise RuntimeError("No outputs in OpenClaw response")
            
            return ChatResponse(
                text=outputs[0].get("text", ""),
                provider_name=self.name,
                model=data.get("model", "unknown"),
                raw=data
            )
            
        except subprocess.TimeoutExpired:
            raise TimeoutError("OpenClaw inference timed out after 60 seconds")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON response from OpenClaw: {e}")
        except Exception as e:
            raise RuntimeError(f"OpenClaw provider error: {e}")
    
    def is_available(self) -> bool:
        """检查 openclaw CLI 是否可用"""
        return shutil.which("openclaw") is not None