## [5.15.2] - 2026-06-12

### Fixed
- **store_corrected 多门店误触发 bug**
  - 问题：多门店 Phase B 对所有已确认门店都 emit store_corrected，不区分「确认」和「纠正」
  - 修复：新增系统匹配对比逻辑，仅当用户选的门店 ≠ 系统匹配的门店时才 emit store_corrected
  - 影响范围：多门店 + 单门店两条路径都修复
  - 副作用：每次确认门店时多跑一次 _call_match_store（性能开销可忽略）

### Added
- **submitted_by / corrected_by DB 列**
  - order_feedback 新增 submitted_by TEXT（追踪订单提交人）
  - order_corrections 新增 corrected_by TEXT（追踪纠正人）
- **历史订单回放脚本** scripts/history_replay.py
  - 从 order_feedback 取历史订单重跑 execute()，对比新旧匹配结果
  - 输出 /tmp/history_replay_YYYYMMDD.md
- **准确率对比报告脚本** scripts/accuracy_comparison.py
  - 接收两个版本号参数，按版本分组对比匹配率/确认率/纠正率
  - 支持 --json 输出

## [5.15.1] - 2026-06-11

### Fixed
- **P1-1: 用户补未匹配 SKU 后保留 seq 并按序重排**
  - 问题：补 SKU 时新记录缺少 seq/spec/remark/product_spec，且 append 到末尾导致模板错行
  - 修复：补齐缺失字段 + 按 seq 重排 sku_results
- **P1-2: SKU 修正 update 失败显式报错**
  - 问题：store_key/seq 匹配不到时静默跳过，用户以为已修正实际没生效
  - 修复：记录 applied_updates/failed_updates，有失败时返回 need_sku_confirm + 失败原因
- **P2: 字段标准化层同时输出 phone/address 兼容字段**
  - 问题：只输出 store_phone/store_address，下游可能漏读
  - 修复：同时输出 phone/store_phone、address/store_address

### Added
- 自学习模块：Layer 0 别名表多 SKU 结合 order_unit 选（和 Layer 1 逻辑一致）
- 自学习模块：yaml SKU 别名加载（_load_yaml_sku_aliases）
- 自学习模块：yaml 字段别名加载（_merge_auto_aliases）
- 自学习模块：submitted_by 字段追踪（DB + adapter + collector + execute 参数）
- 自学习模块：分析脚本 analyze_learning_data.py
- 自学习模块：每日别名表汇总 daily_alias_summary.py
- 自学习模块：通知配置 notification_config.yaml + notification_sender.py
- 本地 launchd：com.ai-order.daily-alias-summary.plist
- cron_tasks.txt（服务器迁移用）

**改动文件：**
  • `VERSION`
  • `SKILL.md`
  • `README.md`
  • `CHANGELOG.md`
  • `__init__.py`
  • `tools/_sku_mapper.py`
  • `tools/_field_transformer.py`
  • `learn/schema.sql`
  • `learn/adapter.py`
  • `learn/collector.py`
  • `field_mapping/rules/sku_aliases_auto.yaml`
  • `field_mapping/rules/field_aliases_auto.yaml`

## [5.15.0] - 2026-06-11

### Added
- 新增功能

**改动文件：**
  • `CHANGELOG.md`
  • `README.md`
  • `SKILL.md`
  • `VERSION`
  • `__init__.py`
  • `scripts/test_event_pipeline.py`
  • `tools/_sku_mapper.py`
  • `tools/_store_matcher.py`
  • `tools/_template_generator.py`
**触发来源：** session `auto-monitor`

# Changelog

All notable changes to this skill will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [5.14.0] - 2026-06-11

### Changed
- **选 SKU 时考虑 order_unit 和规格 (金姐指示 - "单位和 sku 是绑定的")**
  - 新增 `_compute_match_score()` 统一打分函数 (Layer 2/2.5/3 共用)
    - 基础权重 + `order_unit == sku_unit` 加成 +0.20 (强信号)
    - `order_spec == db_spec` 加成 +0.10 (中信号)
  - 新增 `_select_unique_best()` 选唯一最高分函数
    - 唯一最高分 → 直接返回,不加 need_confirm
    - 多个并列最高 → 返回 candidates + need_confirm=True
  - 新增 `_build_with_candidates()` 复用 v5.13.2 的 candidates 机制
  - **Layer 1/1b 多候选时按 order_unit 选**：唯一命中不返 candidates, 多个或 0 命中返 candidates
  - **Layer 2 取消 `if clean_name != product_name` 限制**：v5.14.0 修复, 原限制导致 clean_name=果糖=product_name 时 Layer 2 跳过, 但 DB 里 SKU 叫 "果糖/新"必须走 Layer 2
  - **未命中原因**："订单 1 件匹配到瓶"的 bug 根因是 Layer 1/1b 多候选时直接取 first, 没看 order_unit
  - **设计原则**: SKU 和 unit 是绑定的, 不是单独匹配的

### Why
- 金姐 10:52 指出: "理论上来说单位和 sku 是绑定的不是单独匹配的"
- v5.13.0 之前 `_resolve_unit_type()` 会选完 SKU 后按 order_unit 选 unit
- v5.13.0 "用户选 SKU 即选单位" 改动后, order_unit 没人接了, 变成"先选 SKU 再看 unit"
- 实际表现: 订单 1 件匹配到 12 瓶/件 SKU 错误, Layer 2/2.5/3 不看 order_unit, 排序后取 first

### Behavior
- `果糖+桶` → SK230904000008 (桶/小单位) 唯一命中 ✅
- `果糖+箱` → SK230904000009 (箱/大单位) 唯一命中 ✅
- `果糖` (无单位) → candidates 2 个 (小单位/大单位)
- `果糖+件` (件不在DB) → candidates 2 个 (因为 order_unit 没命中任何 SKU)
- **出库数量不换算** (金姐指示): quantity 保持原值, 不按 conversion_ratio 换算

### CI 回归
- 新增 B5/B6 测试用例 (8 个)
- 旧 45 个测试 + 新 8 个 = **53 个测试全过**
- 1 步 SKU 回归 + 1 步版本号核对 = 2 步 CI 全过

## [5.13.3] - 2026-06-11

### Fixed
- **`_clean_product_name` 末尾孤立分隔符 bug（金姐反馈 - 沧州行别营店"果糖-"）**
  - 问题：订单商品名 "果糖-"、"果糖_"、"-果糖" 这类带孤立分隔符的，清洗后仍保留符号
  - 影响：Layer 1/1b 精确匹配失败 → 走 Layer 2 模糊匹配 → 名称相似度只有 66%（无 keyword_boost，因为 "果糖-" 不在 "果糖/新" 里）→ 综合分 0.6 < 0.7 阈值 → 整体未命中
  - 修复：清洗函数末尾追加 `re.sub(r'[-_./\\,;:]+$', '', cleaned)` + `re.sub(r'^[-_./\\,;:]+', '', cleaned)`
  - 修复后 "果糖-" → "果糖" → Layer 2 模糊匹配命中（66%名称+50%规格=0.6，需确认）

### Why I Missed It
- 之前只在 "_clean_product_name" docstring 里写了"保留连接符 -、-、_"
- 没考虑到实际订单数据里 "-" 常作为"残留符号"出现（OCR 错误、人工输入漏字等）
- 金姐反馈后才意识到：-作为分隔符（"D-X-H"）vs -作为孤立符号（"果糖-"）需要区别对待

### Added
- **CI 回归测试** (`scripts/test_sku_mapper_regression.py` + `scripts/ci_regression.sh`)
  - 金姐 09:56 指示："OK，CI自动回归"
  - **45 个测试用例**：32 单元测试（`_clean_product_name` 边界）+ 13 端到端测试（SKU 映射真实 DB）
  - **覆盖**：中间连接符保留、末尾/开头孤立分隔符、两端都有、多连续、括号、空白、真实 SKU (椰子水/果糖/白糖糕D-X-H/浩然奥尔良翅中)
  - **用法**：`bash scripts/ci_regression.sh` 或 `python3 scripts/test_sku_mapper_regression.py`
  - **下次改 `_sku_mapper.py` 前必跑**，避免回归

## [5.13.2] - 2026-06-10

### Changed
- **多候选SKU展示给用户选择**：用户选SKU即选单位（sku_code+unit+unit_type一体）
  - Layer 0/1/1b 多同名SKU时返回 `candidates` 列表 + `need_confirm=True`
  - `comparison_table` 增加 candidates 展示，用户可见所有候选SKU
  - 去掉 `_resolve_unit_type` 后置自动选择，改为用户手动确认

### Fixed
- **`_clean_product_name` 中文括号正则丢失**：`r'[((][^))]*[))]'` 只匹配ASCII括号
  - 修复为 `r'[\uff08(][^)\uff09]*[\uff09)]'`，同时匹配中文（）和英文()
  - 影响：Layer 1b 无法匹配 "浩然奥尔良翅中（10袋）" 类商品名
- 测试：单元测试 12/12，端到端 12/12 = 100%

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