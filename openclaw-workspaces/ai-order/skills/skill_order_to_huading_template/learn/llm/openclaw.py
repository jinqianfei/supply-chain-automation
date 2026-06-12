"""
OpenClaw 平台内嵌模型 Provider
通过 openclaw infer model run 调用平台指定模型
"""
import subprocess
import json
import shutil
from .provider import LLMProvider, ChatRequest, ChatResponse

class OpenClawProvider(LLMProvider):
    """通过 openclaw infer model run 调用平台模型"""
    name = "openclaw"
    
    def __init__(self, config: dict = None):
        """初始化"""
        self.config = config or {}
        self.model = self.config.get("model")  # 由 llm.yaml 配置，不硬编码默认值
    
    def chat(self, req: ChatRequest) -> ChatResponse:
        """使用 OpenClaw 平台模型"""
        full_prompt = f"{req.system}\n\n{req.user}"
        
        try:
            cmd = ["openclaw", "infer", "model", "run",
                   "--prompt", full_prompt, "--json"]
            
            # 如果配置了模型，指定它
            if self.model:
                cmd.extend(["--model", self.model])
            
            result = subprocess.run(
                cmd,
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
                model=data.get("model", self.model),
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
