# LLM Provider 通用化方案

**版本**: v1.0
**日期**: 2026-06-09
**目标**: 订单解析的 LLM 调用从「硬编码 MiniMax/OpenAI」升级为「**配置驱动 + 多 provider + 平台内嵌模型**」
**前置**: 已确认 `openclaw infer model run` 可用，自动用当前 agent 模型（`minimax-portal/MiniMax-M3`），无需 API key

---

## 1. 现状

`tools/_order_parser.py::_call_llm()` 现状：

```python
# 现状：硬编码 2 个 provider
api_key = os.getenv("MINIMAX_API_KEY") or os.getenv("OPENAI_API_KEY")
if not api_key:
    return {"success": False, "error": "未设置 MINIMAX_API_KEY 或 OPENAI_API_KEY"}

if os.getenv("MINIMAX_API_KEY"):
    client = openai.OpenAI(
        api_key=api_key,
        base_url="https://api.minimax.chat/v1",
    )
    response = client.chat.completions.create(model="MiniMax-M2.7", ...)
else:
    client = openai.OpenAI(api_key=api_key)
    response = client.chat.completions.create(model="gpt-4o", ...)
```

**3 大问题**：

| 问题 | 影响 |
|------|------|
| **1. 硬编码 2 个 provider** | 加 Claude / Gemini / DeepSeek / Qwen 都要改代码 |
| **2. API key 必需** | 云端部署时也要配 key，不优雅 |
| **3. 无法用平台模型** | skill 跑在 OpenClaw agent 里，本可以**直接复用 agent 自己的模型**，现在却要单独配 API |

---

## 2. 目标

**配置驱动 + 接口抽象 + 不改代码切换**。

| 维度 | 现在 | 目标 |
|------|------|------|
| Provider 数量 | 2（硬编码）| **N**（YAML 配置，理论无限）|
| 加新 provider | 改代码 | **改 1 行 YAML** |
| 平台内嵌模型 | ❌ | ✅ 默认 `openclaw` provider |
| API key | 必需 | **可选**（平台 provider 不要）|
| 故障回退 | 无 | **fallbacks 链** |
| 跟 G2 ChannelAdapter 对称 | — | **同设计思想** |

---

## 3. 架构

```
┌──────────────────────────────────────────────────────┐
│ tools/_order_parser.py（业务侧，**几乎不改**）        │
│                                                      │
│   response_text = LLMRouter.chat(                    │
│       system=system_msg,                             │
│       user=user_msg,                                 │
│   )                                                  │
│   # 返回 string，调用方完全无感                       │
└──────────────────────┬───────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│ learn/llm/router.py — 路由 + 回退                     │
│   • 读 config/llm.yaml                               │
│   • 拿到 default provider + fallbacks                │
│   • 依次尝试，失败自动下一个                          │
│   • 记录调用日志（learn/llm_log 表，可选）            │
└──────────────────────┬───────────────────────────────┘
                       │
        ┌──────────────┼──────────────┬──────────────┐
        ▼              ▼              ▼              ▼
   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐
   │OpenClaw │   │OpenAI   │   │OpenAI   │   │Custom   │
   │Provider │   │Provider │   │Compat   │   │HTTP     │
   │(subproc)│   │(SDK)    │   │(SDK)    │   │Provider │
   └────┬────┘   └────┬────┘   └────┬────┘   └────┬────┘
        │             │             │             │
        ▼             ▼             ▼             ▼
   openclaw      api.openai    base_url        自定义
   infer model   .com          + api_key      endpoint
   run --prompt                 任意 OpenAI
   --json                       兼容服务
```

**关键不变量**：
- `_order_parser.py` **不 import** `learn/llm/*` 的具体实现，**只**调 `LLMRouter.chat()`
- 加新 provider = YAML 加一段 + `learn/llm/` 加一个 Provider 文件
- **不改 `_order_parser.py` 也能加 provider**

---

## 4. 接口定义

### 4.1 Provider 抽象（伪代码）

```python
# learn/llm/provider.py
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class ChatRequest:
    system: str
    user: str
    model: str = None          # 可选覆盖
    temperature: float = 0.1
    max_tokens: int = 4000

@dataclass
class ChatResponse:
    text: str
    provider_name: str
    model: str
    raw: dict                 # 原始响应，调试用

class LLMProvider(ABC):
    name: str                 # "openclaw" / "openai" / "minimax" ...

    @abstractmethod
    def chat(self, req: ChatRequest) -> ChatResponse: ...
    
    @abstractmethod
    def is_available(self) -> bool: ...   # 探活（不实际调 API）
```

### 4.2 Router 接口

```python
# learn/llm/router.py
class LLMRouter:
    def __init__(self, config_path: str = "config/llm.yaml"): ...
    def chat(self, system: str, user: str, **kwargs) -> ChatResponse: ...
    def list_providers(self) -> List[str]: ...
    def get_default(self) -> str: ...
```

### 4.3 4 种 Provider 实现

#### A. `OpenClawProvider`（**金姐要的核心**）

```python
# learn/llm/openclaw.py
class OpenClawProvider(LLMProvider):
    name = "openclaw"
    
    def chat(self, req: ChatRequest) -> ChatResponse:
        full_prompt = f"{req.system}\n\n{req.user}"
        result = subprocess.run(
            ["openclaw", "infer", "model", "run",
             "--prompt", full_prompt, "--json"],
            capture_output=True, text=True, timeout=60
        )
        data = json.loads(result.stdout)
        return ChatResponse(
            text=data["outputs"][0]["text"],
            provider_name="openclaw",
            model=data["model"],        # 自动用当前 agent 模型
            raw=data
        )
    
    def is_available(self) -> bool:
        return shutil.which("openclaw") is not None
```

**优势**：零 API key、自动用 agent 模型、跨环境零配置。

#### B. `OpenAIProvider`（OpenAI 官方）

```python
# learn/llm/openai.py
class OpenAIProvider(LLMProvider):
    name = "openai"
    
    def chat(self, req: ChatRequest) -> ChatResponse:
        client = openai.OpenAI(api_key=self.config["api_key"])
        resp = client.chat.completions.create(
            model=self.config.get("model", "gpt-4o"),
            messages=[
                {"role": "system", "content": req.system},
                {"role": "user", "content": req.user}
            ],
            temperature=req.temperature,
            max_tokens=req.max_tokens
        )
        return ChatResponse(
            text=resp.choices[0].message.content,
            provider_name="openai",
            model=resp.model,
            raw=resp.model_dump()
        )
```

#### C. `OpenAICompatProvider`（**最通用**——支持 MiniMax、DeepSeek、Qwen、Kimi 等所有 OpenAI 兼容 API）

```python
# learn/llm/openai_compat.py
class OpenAICompatProvider(LLMProvider):
    """所有兼容 OpenAI Chat Completions 接口的服务都走这个"""
    name = "openai_compat"
    
    def __init__(self, config: dict):
        self.base_url = config["base_url"]
        self.api_key = config["api_key"]
        self.model = config["model"]
        self.name = config.get("alias", self.base_url)  # 自定义名称
    
    def chat(self, req: ChatRequest) -> ChatResponse:
        client = openai.OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        resp = client.chat.completions.create(
            model=req.model or self.model,
            messages=[...],
            temperature=req.temperature,
            max_tokens=req.max_tokens
        )
        return ChatResponse(
            text=resp.choices[0].message.content,
            provider_name=self.name,
            model=resp.model,
            raw=resp.model_dump()
        )
```

**支持的 provider**（YAML 配置即用）：
- MiniMax：`https://api.minimax.chat/v1` + `MiniMax-M2.7`
- DeepSeek：`https://api.deepseek.com/v1` + `deepseek-chat`
- 通义千问：`https://dashscope.aliyuncs.com/compatible-mode/v1` + `qwen-plus`
- 月之暗面 Kimi：`https://api.moonshot.cn/v1` + `moonshot-v1-8k`
- 智谱 GLM：`https://open.bigmodel.cn/api/paas/v4` + `glm-4-plus`
- 自部署 vLLM/Ollama：`http://localhost:8000/v1` + `qwen2.5-7b`

#### D. `CustomHTTPProvider`（兜底，支持非 OpenAI 协议）

```python
# learn/llm/custom_http.py
class CustomHTTPProvider(LLMProvider):
    """通用 HTTP POST 调用，用户自己定义 request/response 解析"""
    def chat(self, req: ChatRequest) -> ChatResponse:
        resp = requests.post(
            self.config["url"],
            json={
                "system": req.system,
                "user": req.user,
                **self.config.get("extra_body", {})
            },
            headers=self.config.get("headers", {}),
            timeout=self.config.get("timeout", 60)
        )
        data = resp.json()
        return ChatResponse(
            text=self._extract_text(data),    # 用户自定义提取规则
            provider_name=self.name,
            model=data.get("model", "unknown"),
            raw=data
        )
```

**适用**：Anthropic Claude（不支持 OpenAI 协议）、Google Gemini、自研 API。

---

## 5. 配置文件

`config/llm.yaml`（**新文件**）：

```yaml
# === LLM Provider 配置 ===
# 加新 provider = 在 providers 下加一段，**不改代码**

# 默认 provider（必须存在）
default: openclaw

# 故障回退链（按顺序尝试）
fallbacks:
  - minimax
  - openai
  - deepseek

providers:
  # ===== 平台内嵌模型（推荐默认）=====
  openclaw:
    type: openclaw
    # 无需任何配置，自动用当前 OpenClaw agent 的模型
    # 当前模型: minimax-portal/MiniMax-M3

  # ===== OpenAI 兼容 API（一个 type 通吃所有）=====
  minimax:
    type: openai_compat
    alias: "MiniMax"
    base_url: "https://api.minimax.chat/v1"
    api_key: "${MINIMAX_API_KEY}"
    model: "MiniMax-M2.7"
    timeout: 60

  openai:
    type: openai
    api_key: "${OPENAI_API_KEY}"
    model: "gpt-4o"
    timeout: 60

  deepseek:
    type: openai_compat
    alias: "DeepSeek"
    base_url: "https://api.deepseek.com/v1"
    api_key: "${DEEPSEEK_API_KEY}"
    model: "deepseek-chat"
    timeout: 60

  qwen:
    type: openai_compat
    alias: "Qwen"
    base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
    api_key: "${QWEN_API_KEY}"
    model: "qwen-plus"
    timeout: 60

  kimi:
    type: openai_compat
    alias: "Kimi"
    base_url: "https://api.moonshot.cn/v1"
    api_key: "${KIMI_API_KEY}"
    model: "moonshot-v1-8k"
    timeout: 60

  # ===== 非 OpenAI 协议（用 custom_http 兜底）=====
  claude:
    type: custom_http
    alias: "Claude"
    url: "https://api.anthropic.com/v1/messages"
    headers:
      "x-api-key": "${ANTHROPIC_API_KEY}"
      "anthropic-version": "2023-06-01"
    extra_body:
      model: "claude-3-5-sonnet-20241022"
      max_tokens: 4000
    # 提取规则：response.content[0].text
    text_path: "content.0.text"
    timeout: 60
```

---

## 6. 改造点

```
修改：
  tools/_order_parser.py              # _call_llm() 缩成 5 行：LLMRouter.chat()

新增：
  learn/llm/__init__.py               # 导出 Router
  learn/llm/provider.py              # 接口 + 数据类
  learn/llm/openclaw.py               # 平台内嵌模型（subprocess）
  learn/llm/openai.py                # OpenAI 官方
  learn/llm/openai_compat.py         # 通用 OpenAI 兼容
  learn/llm/custom_http.py           # 通用 HTTP 兜底
  learn/llm/router.py                # 路由 + 回退链
  config/llm.yaml                    # 配置文件
  config/llm.yaml.example            # 模板（无敏感信息）
  tests/test_llm_router.py           # Router 测试
  tests/test_llm_providers.py        # 各 Provider 测试（用 mock）
  docs/LLM_PROVIDER_REFACTOR_PLAN.md # 本文档
```

**总工作量**：2-3 天
- 0.5 天：接口 + 数据类
- 1 天：4 个 Provider 实现 + Router
- 0.5 天：配置 + 测试
- 0.5 天：集成到 `_order_parser.py` + 真实订单回归

---

## 7. 改造后 `_call_llm` 长啥样

```python
# tools/_order_parser.py 改造后（约 5 行）
from learn.llm import LLMRouter

_router = None

def _get_router():
    global _router
    if _router is None:
        _router = LLMRouter("config/llm.yaml")
    return _router

def _call_llm(text_content: str, content_type: str = "text") -> Dict[str, Any]:
    """调用 LLM 解析订单文本（新版：通过 Router）"""
    try:
        prompt = _build_prompt(text_content, content_type)
        resp = _get_router().chat(
            system="你是一个专业的订单数据提取专家。请从用户提供的订单内容中准确提取结构化信息。",
            user=prompt
        )
        return _parse_llm_raw(resp.text)
    except Exception as e:
        return {"success": False, "error": f"LLM调用失败: {str(e)}"}
```

**对比**：60 行 → 12 行，**业务逻辑完全无感**。

---

## 8. 优势

| 优势 | 说明 |
|------|------|
| **加 provider 零代码** | YAML 加一段 |
| **平台内嵌模型** | 默认 `openclaw`，零 API key、零配置 |
| **故障回退** | `default` 挂了自动试 `fallbacks` |
| **跟 G2 对称** | 跟 `ChannelAdapter` 同一设计思想：**接口抽象 + 配置驱动 + 不改代码切换** |
| **可观测性** | Router 自动记录每次调用：`learn/llm_log` 表（provider / model / latency / success / error）|
| **成本控制** | 用户可指定「便宜的走 minimax、关键任务走 openai」|

---

## 9. 风险点

| 风险 | 缓解 |
|------|------|
| `openclaw infer` 阻塞主线程 | subprocess 60s timeout；失败自动回退 |
| 平台模型不可用（agent 未配置）| `is_available()` 探活 + fallbacks 链 |
| OpenAI 协议各家细节差异（reasoning_content、tool_calls）| 仅取 `choices[0].message.content`，屏蔽差异 |
| API key 泄露到 git | YAML 用 `${ENV_VAR}` 引用，真实 key 走 `.env`（已有机制）|
| 用户乱配 provider 导致连锁失败 | `is_available()` 启动时校验，配错立即报错 |

---

## 10. 实施步骤（3 天）

| 步 | 内容 | 工作量 | 验收 |
|----|------|--------|------|
| 10.1 | 接口 + 数据类（`provider.py`）+ Router 骨架（`router.py`）| 0.5 天 | 单元测试：Router 选 default |
| 10.2 | 4 个 Provider 实现（`openclaw.py` / `openai.py` / `openai_compat.py` / `custom_http.py`）| 1 天 | mock 测试 4 个 Provider 返回正确 |
| 10.3 | `config/llm.yaml` 模板 + 真实接 minimax + openai 测 | 0.5 天 | 真实 API 调用成功，JSON 解析对 |
| 10.4 | 改造 `_call_llm` 接入 Router + 删掉硬编码 | 0.5 天 | 真实订单回归不破 |
| 10.5 | 单元测试 + 集成测试 + SKILL.md/CHANGELOG/VERSION 5.9.0 → 5.11.0 | 0.5 天 | `test_llm_router.sh` 全过 |

---

## 11. 验收标准（完成定义）

- [ ] 4 个 Provider 全部实现 + 测试通过
- [ ] `config/llm.yaml` 配 6 个 provider（openclaw / minimax / openai / deepseek / qwen / kimi）跑通
- [ ] `default` provider 切换**只改 YAML 不改代码**
- [ ] fallbacks 链真实生效：kill `default` API → 自动试下一个
- [ ] `_call_llm` 从 60 行缩到 12 行
- [ ] 真实订单回归（创宇/小江溪/王小五）准确率不破
- [ ] `VERSION` 5.9.0 → 5.11.0 / `CHANGELOG.md` 补 [5.11.0] 条目
- [ ] git tag `v5.11.0`

---

## 12. 跟 Phase 3.0 的关系

- **不冲突**：Phase 3.0 改的是字段映射；LLM Provider 改的是解析调用
- **可并行**：LLM Provider 是 5.11.0，Phase 3.0 是 5.10.0，**先后顺序**或**同时**都行
- **依赖**：
  - Phase 3.0.4（prompt 注入字段 hint）通过 Router 注入，跟 LLM Provider 改造**正交**
  - 建议：**先做 LLM Provider**（基础组件），再做 Phase 3.0（在 LLM 之上注入 hint）

---

**文档版本**: v1.0
**最后更新**: 2026-06-09
**下次更新**: 评审通过后冻结为 v1.0；如调整记 v1.1