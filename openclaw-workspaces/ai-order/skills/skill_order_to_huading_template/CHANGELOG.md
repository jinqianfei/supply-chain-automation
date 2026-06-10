# Changelog

All notable changes to this skill will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [5.13.1] - 2026-06-10

### Changed
- **SKU匹配与单位选择解耦**：名称匹配和单位选择分成两个独立步骤
  - `_map_single_in_batch()` 只做名称匹配，返回 sku_name
  - `map_sku_batch()` 后置步骤：用 sku_name 查同名 SKU + 订单单位精确匹配选择
  - `_resolve_unit_type()` 简化为：单位精确匹配 → 匹配不上用第一个 SKU
  - `map_sku()` 委托给 `map_sku_batch()` 保持逻辑一致
- 测试：单元测试 12/12，端到端 12/12 = 100%

## [5.13.0] - 2026-06-10

### Fixed
- **P1 bug：unit_type 硬编码“大单位”导致所有订单始终返回大单位**
  - 根因：`_sku_mapper.py` 所有 Layer SQL 含 `ORDER BY CASE WHEN unit_type = '大单位' THEN 0 ELSE 1 END`，强制优先返回大单位 SKU
  - 表现：813 个同名多SKU商品（占全部 45%）始终返回大单位，无视订单实际数量/单位
  - 修复：新增 `_resolve_unit_type()` 函数，三级优先级选择出库单位：
    1. **订单单位精确匹配** — order_unit 与 SKU.unit 字段匹配
    2. **“件”特殊规则** — 订单单位=“件”时直接选大单位（件=整件出库）
    3. **数量+ratio 匹配** — order_quantity >= max_ratio → 大单位，否则 → 小单位
  - 多个同 ratio 候选时设置 `need_confirm=True` 让用户确认
  - 同步修复 `_template_generator.py` / `__init__.py` 中 6 处硬编码“大单位”默认值
  - 测试：`tests/test_unit_type_fix.py` — 单元测试 17/18，端到端 12/12 = 100%

### Changed
- `map_sku()` 新增 `order_quantity` 参数（向后兼容，默认=1）
- `_map_single_in_batch()` 新增 `quantity` 参数传递
- `map_sku_batch()` 中 `alias_rows` 改为 `alias_groups` 支持同名多SKU
- SQL 去除所有 `ORDER BY CASE WHEN unit_type = '大单位'` 硬编码排序

## [5.12.0] - 2026-06-10

### Fixed
- **P1 bug：多门店 + 单 confirmed_store 不应作用于所有门店**
  - 根因：多门店循环 `for store_key, store_data in stores_dict.items()` 里 `if confirmed_store: si = confirmed_store` 用同一个确认处理所有门店
  - 表现：多门店订单只传 1 个 confirmed_store 时，Excel 所有行 store_code 用第 1 门店
  - 修复：引入 `confirmed_stores: Dict[str, Dict[str, Any]]`，按 store_key 独立查找确认
  - 验证：`scripts/test_execute_confirmation_flow.py::test_single_confirmed_store_does_not_apply_to_all_multi_store_entries` ✅

### Added
- `_merge_confirmed_store(confirmed_stores, confirmed_store)`: 兼容单/批两种 confirmed_store 传参（向后兼容）
- `_confirmed_store_for(confirmed_stores, store_key, store_name)`: 按 store_key 查找确认（fallback 到 store_name + _store_key）
- `_order_cache_with_confirmations(order_data, confirmed_stores)`: 缓存订单数据 + 已确认门店（用于多轮确认）
- `_import_skill_attr(module_path, attr_name)`: 模块属性加载（fallback 支持，兼容无 `skills` 顶层包）
- `_clear_proxy_env()`: 集中清理代理环境变量
- `scripts/test_execute_confirmation_flow.py`: 2 项 execute() 确认检查点回归测试（151 行）
- `scripts/test_execute_import_fallback.py`: import fallback 回归测试

### Changed
- `execute()` 签名：`confirmed_store: Dict = None`（保留向后兼容）
  - 内部：`confirmed_stores = _merge_confirmed_store({}, confirmed_store)` 转为 dict
  - 多门店循环：每个门店独立 `_confirmed_store_for(confirmed_stores, store_key, store_name)`
  - 未确认门店：返回 `need_store_confirm=True` + `order_data_cache._confirmed_stores` 携带已确认门店
- `_store_confirm_response()` 重构：支持 `store_key` + `order_data_cache` + `confirmed_stores` 参数
- README.md / SKILL.md 同步 v5.12.0 API 变更

### Verified
- `python3 scripts/test_execute_confirmation_flow.py` ✅ PASSED（含 P1 bug 回归测试）
- `python3 scripts/test_execute_import_fallback.py` ✅ PASSED
- `python3 scripts/test_event_pipeline.py` ✅ 4/4 全过（回归无破坏）

### Notes
- 本版本作者：金姐 / 自动 commit hook（修改时间 2026-06-10 10:57:33，AI 提交时未注意到，作者待确认）
- B（推 tag）暂未执行：skill 的 git repo 没有任何 remote（已在汇报 #1 标记）

## [5.11.2] - 2026-06-09

### Added
- **配置统一化**：消除代码中的硬编码配置
  - 华鼎 31 字段顺序统一从 `config/template_defaults.yaml` 读取（不再在多处硬编码）
  - 数据库表名常量统一到 `db/table_names.py`（SKU_TABLE / WAREHOUSE_TABLE 等）
  - 新增 `config/template_defaults.yaml`：华鼎字段定义源头
  - 新增 `db/table_names.py`：所有表名的常量定义

### Changed
- `tools/_template_generator.py` 改用 `get_huading_fields()` 从 yaml 读取
- `tools/_sku_mapper.py` 等调用方改用 `SKU_TABLE` / `WAREHOUSE_TABLE` 常量
- `config/__init__.py` 新增 `get_huading_fields()` 函数提供字段配置

### Notes
- 本次改动从 v5.11.1 的 P1 优化中提取并正式发布
- 之前 v5.11.1 的 CHANGELOG 已包含此改动（抽到 yaml / 抽表名常量），但未单独标记版本

## [5.11.1] - 2026-06-09

### Added
- **硬编码清理**：消除所有 P0/P1 机器特定/环境依赖
  - P0 修复：RDS 主机 fallback（`agenthub-db...` → localhost）、AWS IP 改环境变量、SKU mapper 调统一连接、sync_check 改 `$HOME`、测试路径改 tempfile
  - P1 修复：抽 `_load_dotenv_to_environ()` 统一函数、抽 `HUADING_FIELDS` 到 yaml（消除双定义）、抽表名常量到 `db/table_names.py`
  - 评估：移植成熟度从 ⭐⭐½ 提升到 ⭐⭐⭐ (跨机器可跑)
  - 新增 `DOTENV_PATH` 环境变量可指定 .env 文件位置
  - 新增 `AWS_PUBLIC_IP` / `AWS_FILE_PORT` 环境变量控制文件下载 URL

### Fixed
- **关键 bug**：`_match_sku()` 返回的 `sku_results` 缺 `quantity`/`unit`/`spec`/`seq` 字段
  - 根因：`tools/_sku_mapper.py:map_sku_batch()` 调用 `_build_result()` 构造匹配结果，但 `_build_result` 只返回匹配元数据（sku_code/sku_name/unit_type），不返回订单原 quantity
  - 表现：调用方 `__init__._match_sku` 用 `r.get("quantity", 0)` 拿不到 → 默认 0 → 最终 31 字段 Excel 的「出库数量」列恒为 0
  - 修复：在 `map_sku_batch` 循环里显式注入 `result["quantity"] = item.get("quantity", 0)` 等
  - 影响：v5.9.0 commit message 声称修复「_build_result 缺字段」但**实际未覆盖 quantity**，v5.11.0 LLM Router 重构也未涉及 → 5.11.1 补齐

### Verified
- 端到端用 2 个真实订单回归测试（`docs/test_data/test_set_A_history回流.json`）：
  - **1号 洪洪通** (1店1项 椰子水950ml 10件) → `SK231013000200` 大单位 12瓶/件 → 出库数量=10 ✅
  - **9号 天津仓** (2店11项) → 11/11 全部 GT SKU 匹配 → 出库数量=2,1,1,1,1,1,1,2,2,1,2 ✅
  - **总计 12/12 = 100% GT 准确率**

### Notes
- 测试 xlsx 临时放在 `data/test_orders/`，如不需要可删
- 临时测试脚本 `test_order9_e2e.py` 可删
- `_build_result()` 未改（避免破坏 Layer 2/3 模糊匹配的其它调用方）

## [5.10.0] - 2026-06-06

### Added
- **技术锁（v5.10.0 主体）**：`OrderToHuadingTemplate` 类通过 `__getattribute__` 拦截内部函数调用
- 防止 AI 跳过 `execute()` 主入口直接调用 `_match_store()` / `_match_sku()` 等内部函数
- 公开接口白名单机制（`__公开接口__ = ['execute', 'tools_parse', 'tools_transform']`）
- 内部初始化白名单（`__内部初始化__ = ['_load_warehouse_mapping', '_load_field_mapping', '_check_db_connection', '_init_db_repos']`），仅 `__init__` 期间可绕过技术锁

### Changed
- 所有内部方法（`_` 前缀）默认对 AI 不可见，直接 `.attr` 访问抛 `OrderSkillError("E001")`
- 业务内部调用绕过技术锁：`object.__getattribute__(self, '_match_sku')` 模式（不影响运行时）
- 错误码 `E001` 复用（与"文件不存在"共码，但 detail 区分）

### Notes
- 5.9.1 增量 patch（仅 bump VERSION）曾被 `git reset` 撤销，但 5.9.0 主体（技术锁）保留到本版本
- SKILL.md 头 `5.9` 与 VERSION/CHANGELOG 此前未同步，5.10.0 落地时一并补齐
- 技术锁仅拦截 Python 层 `getattr`，不影响 subprocess / DB driver / 文件 I/O

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