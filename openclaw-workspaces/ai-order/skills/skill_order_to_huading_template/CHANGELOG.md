# Changelog

All notable changes to this skill will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [5.9.0] - 2026-06-05

## [5.11.0] - 2026-06-09

### Added
- **LLM Provider 重构**：从硬编码（MiniMax/OpenAI）升级为配置驱动的多 provider 系统
- 新增 `learn/llm/` 模块：4 种 Provider 实现（OpenClaw/OpenAI/OpenAICompat/CustomHTTP）
- 新增 `config/llm.yaml`：加新 provider 只改 YAML，不改代码
- **默认使用 OpenClaw 平台内嵌模型**：`openclaw infer model run`，零 API key、自动用当前 agent 模型
- 故障回退链：default 挂了自动试 fallbacks
- `_call_llm` 从 60 行缩到 12 行，业务逻辑完全无感

### Changed
- `tools/_order_parser.py` 接入 LLMRouter

### Notes
- 本次 LLM Provider 改造后，数据库配置统一使用 .env 中的环境变量（默认 RDS 云端）- 本次重构解决了「skill 无法直接用平台模型」的问题
- 与 Phase 3.0 字段名采集正交，可独立演进
- 建议：先部署 5.11.0 验证 LLM Router，再做 Phase 3.0
### Added
- **技术锁**：`OrderToHuadingTemplate` 类通过 `__getattribute__` 拦截内部函数调用
- 防止 AI 跳过 `execute()` 主入口直接调用 `_match_store()` / `_match_sku()` 等内部函数
- 公开接口白名单机制：`execute()` / `parse_only()` / `validate_db()` / `get_version()`

### Changed
- 所有内部方法（`_` 前缀）通过 `__内部初始化__` 字典存储，对外不可见
- AI 必须通过 `skill.execute()` 入口调用

### Notes
- 本次 LLM Provider 改造后，数据库配置统一使用 .env 中的环境变量（默认 RDS 云端）- 本次修改的对话背景：5.9.1 增量 patch（仅 bump VERSION）被 reset 撤销，但 5.9.0 主体（技术锁）保留
- SKILL.md 头 5.9 与 VERSION/CHANGELOG 此前未同步，本次补齐

### Phase 1 — 自适应学习系统 (2026-06-08)

#### Added
- **`events/` 事件总线**：极简进程内 EventBus（40 行，零外部依赖），支持 on/off/emit/clear
- **`learn/` 反馈采集器**：`FeedbackCollector` 订阅 10 个事件并写入数据库
  - `order_feedback` 主表（订单级处理反馈）
  - `order_corrections` 子表（结构化用户纠正记录）
  - `layer_success_rate` 统计表（动态计算 5+6 层匹配成功率）
  - 3 个 view：`v_daily_feedback_stats` / `v_layer_success_rate`
- **`scripts/version_check.sh`**：启动时核对 VERSION/SKILL.md/CHANGELOG 三处版本号一致
- **`scripts/test_event_pipeline.py`**：4 项端到端测试（EventBus / Collector / DB 写入 / 模块集成）

#### Changed
- **`__init__.py`**：埋入 6 个 `EventBus.emit()` 调用（4 个事件 × 多门店/单门店两处）
  - `store_confirm_needed`（门店需确认）
  - `store_confirmed`（门店已确认）
  - `order_complete`（订单完成）
  - `user_modified`（用户修改字段）
- **`__init__.py` 顶部**：增加 EventBus 懒加载导入 + `try/except ImportError` 保护
- **`__init__.py` execute() 入口**：生成 `order_session_id` (uuid4) + `_started_ms` 计时
- **数据库 `order_feedback` 表**：新增 `data_source TEXT` 列（追踪数据来源）
- **`version_check.sh`**：从 `grep -P` 改为 `grep -E`（兼容 BSD grep，macOS 默认）
- **SKILL.md 头**：版本号从 `5.9` 修正为 `5.9.0`，与 VERSION/CHANGELOG 对齐

#### Noted
- 本次只做 Phase 1（数据采集），Phase 2（自动别名学习） / Phase 3（健康度评估）未实施
- 6 个 emit 中，store_confirm_needed / store_confirmed 各 2 处（多门店版+单门店版），order_complete / user_modified 各 1 处

---

## [5.8.0] - 2026-06-01

### Added
- 数据库合并：`product_sku` + `product_name_alias` 双表支持
- SKU 匹配 5 层逻辑（精确→模糊→别名→规格→兜底）
- 新增 `product_name_alias` 表（商品名别名表），支持 102+ 条别名记录

### Changed
- 订单解析流程优化，支持更多输入格式

### Fixed
- SKU 匹配兜底逻辑修复

---

## Template

```markdown
## [X.Y.Z] - YYYY-MM-DD

### Added
- 新增功能说明

### Changed
- 变更内容说明

### Fixed
- 修复的问题

### Notes
- 本次 LLM Provider 改造后，数据库配置统一使用 .env 中的环境变量（默认 RDS 云端）- 本次修改的对话背景 session: om_xxx
```