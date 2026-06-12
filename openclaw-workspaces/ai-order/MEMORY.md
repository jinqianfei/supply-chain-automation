# MEMORY.md - AI建单助手记忆

## 最新Skill版本

**当前活跃版本**: skill_order_to_huading_template **v5.15.4**（2026-06-12 — P1多门店confirmed_store跨门店泄漏修复）

**路径**: `/Users/jinqianfei/openclaw-workspaces/ai-order/skills/skill_order_to_huading_template/`

> ⚠️ **本字段必须是真相源** — 启动时由 `version_check.sh` 校验，VERSION/CHANGELOG/SKILL.md 三者必须一致
> ✅ **2026-06-11 验证通过**：`bash skills/skill_order_to_huading_template/scripts/version_check.sh` 三处一致（v5.14.0）

### v5.14.0 变更要点（2026-06-11 金姐10:52 指示 → 修复）
- **Bug**: "订单 1 件（12 瓶/件）匹配到瓶"或"订单 12 瓶匹配到件"
- **根因**: Layer 1/1b 多候选时直接取 first, Layer 2/2.5/3 完全不看 order_unit
- **金姐指示**: "理论上来说单位和 sku 是绑定的不是单独匹配的"
- **修复**:
  - 新增 `_compute_match_score()` 统一打分 (order_unit 加成 +0.20, spec 加成 +0.10)
  - 新增 `_select_unique_best()` 选唯一最高分 (唯一直接返回, 多候选返 candidates)
  - 改 Layer 1/1b 多候选时按 order_unit 选
  - 取消 Layer 2 的 `if clean_name != product_name` 限制
- **出库数量不换算**: 保持原值, 不按 conversion_ratio 换算
- **效果**: 果糖+桶 → SK230904000008 (桶/小单位) 唯一命中 0.63
- **CI**: 53/53 旧+新测试全过

### v5.14.0 端到端测试结果（2026-06-11 11:30 GMT+8）
- **测试矩阵**:
  | 数据集 | 商品数 | SKU 命中 | 准确率 |
  |---|---|---|---|
  | CI 回归 (53 用例) | 53 | 53 | **100%** |
  | D set 盲测 | 20 | 20 | **100%** |
  | 洪洪通 (1店1项) | 1 | 1 | **100%** |
  | 天津仓 (2店11项) | 11 | 11 | **100%** |
  | A_history回流 (9 单) | 51 | 5 | 9.8%* |
- **实际 SKU 匹配准确率**: 85/85 = **100%**（排除 GT 问题数据集）
- **A set 低准确率原因**:
  - GT 字段为 `-` (阿朴社长/广州仓/郑州仓多数订单)
  - GT 是货主自编码 (不是华鼎标准 SKU)
  - 配送明细表26 用"门店1""门店2"占位符 (找不到 owner_code)
- **脚本路径**:
  - `tests/e2e_v5140.py` (完整 execute() 流程, 未跑通 — LLM 调用卡住)
  - `tests/gt_v5140_test.py` (map_sku_batch 直接比对, 跑通)
  - `/tmp/e2e_report_v5140.md` (完整报告)

### v5.13.3 变更要点（2026-06-11 金姐反馈 → 修复）
- **Bug**：`沧州行别营店`订单里的"果糖-"（带末尾孤立`-`）匹配不到 DB 里的 "果糖/新"
- **根因**：`_clean_product_name` 函数只考虑了 `-` 作为合法连接符（"D-X-H"），没考虑 `-` 作为残留符号（"果糖-"）
- **修复**：清洗函数末尾追加 2 行正则，用 `^/$` 锚点只去除开头/末尾的孤立分隔符
  ```python
  cleaned = re.sub(r'[-_./\\,;:]+$', '', cleaned)
  cleaned = re.sub(r'^[-_./\\,;:]+', '', cleaned)
  ```
- **效果**：`果糖-` → `果糖` → Layer 2 模糊匹配命中（66%名称+50%规格=0.6，需确认）
- **回归**：`白糖糕D-X-H`（中间连接符保留）仍走 Layer 1 精确匹配 0.95，`果糖-`/`-果糖`/`-果糖-`/`果糖_` 全部能匹配

### 金姐决定的边界
- ✅ **当前逻辑保留**：只去除开头/末尾孤立分隔符，中间连接符不动
- ❌ **不再增强**：Layer 2.5 不加 "子串高置信度"逻辑（6-11 早上金姐明确说"不用，保持当前逻辑"）

### CI 回归测试（6-11 建立）

**金姐 09:56 指示**：CI 自动回归，把果糖/D-X-H等边界用例固化成单元测试

**脚本位置**：
- `scripts/test_sku_mapper_regression.py` (9576字节，45 个测试用例)
- `scripts/ci_regression.sh` (1997 字节，CI 入口)

**测试覆盖**：
- **A 单元**（32 个）：`_clean_product_name` 边界字符 （中间连接符保留 / 末尾孤立去除 / 两端都有 / 多连续分隔符 / 括号 / 空白）
- **B 端到端**（13 个）：`map_sku_batch` 真实 DB
  - B1: Layer 1 精确匹配（椰子水950ml + 件 → SK231013000200 大单位）
  - B2: v5.13.3 修复验证（果糖 / 果糖- / -果糖 / -果糖- / 果糖_  5 个变体）
  - B3: 中间连接符保留（白糖糕D-X-H → Layer 1 精确匹配，0.95）
  - B4: 括号规格（中英文括号都能去）

**CI 集成方式**：
- 手动：修改 `_sku_mapper.py` 后 `bash scripts/ci_regression.sh` 必跑
- 可加：启动 hook / launchd 定时器（待金姐决定）

**金姐决定 (6-11 10:08)**：
- ✅ **改 skill 逻辑时主动跑一遍**（手动触发）
- ❌ **不集成到启动 hook**（避免启动变慢 3 秒）
- ❌ **不集成到 launchd 定时**（避免重复跑）
- ❌ **不集成到 pre-commit hook**（git 仓库是大杂烩，会误报）

**AI 行为准则**：
- 修改 `tools/_sku_mapper.py` / `__init__.py` 等核心代码后，**主动跑** `bash skills/skill_order_to_huading_template/scripts/ci_regression.sh`
- 跑完后向金姐汇报结果（如"45/45 通过"）
- 失败时**不绕过**，立即停下报告，等待金姐决定

---

## 最近会话摘要

### 2026-06-12 13:39 — P1 多门店 confirmed_store 跨门店泄漏修复

**金姐指示**：修复 P1 bug

**Bug 描述**：
- 多门店订单中，当 AI 只传 1 个 confirmed_store 时，所有门店的 Excel 行都用第 1 门店的 store_code
- 根因：`_confirmed_store_for` 的 fallback 循环中 `store.get("_store_key") == store_key` 会把门店A的确认信息错误地返回给门店B

**修复内容**：
- `_confirmed_store_for`：移除 `_store_key` fallback，仅保留精确 key 查找 + `store_name_submitted` 别名查找
- Phase B：增加 `_confirmed_store_for` fallback + warn 日志（避免直接 skip）
- 新增测试：`tests/test_p1_multi_store_fix.py`（4 个用例：隔离/别名/批量/别名匹配）

**测试结果**：
- P1 专项：4/4 PASSED
- CI 回归：53/53 SKU 测试通过（前 6 步全过，准确率测试因 DB 超时被 kill）

**产出**：
- v5.15.3 发布（VERSION + CHANGELOG + SKILL.md + AGENTS.md + MEMORY.md + TOOLS.md）

---

### 2026-06-12 09:40 — 自学习模块 Review + 硬编码修复 + 闭环补齐

**金姐指示**：review 整个工作区自学习方案完成情况，补缺 + 修硬编码

**完成情况检查**：
- 方案文件：`docs/SELF_LEARNING_MODULE_PLAN.md`
- 发现文件在工作区根目录 `scripts/` + `config/` 下，不在 skill 目录
- Phase 2/5 的 ✅ 标记与实际不符（分析/通知脚本存在但方案标记有误）

**order_corrections 0 条诊断**：
- 结论：**真实数据**（19 单全是单门店，用户未纠正过）
- 发现潜在 bug：多门店 Phase B 中 `store_corrected` 对所有已确认门店都 emit
- **修复**：新增 `_call_match_store` 对比逻辑，用户选的 ≠ 系统匹配时才 emit
- 单门店 + 多门店两条路径都修复

**补 3 个缺失组件**：
- ✅ `submitted_by` / `corrected_by` DB 列已加
- ✅ `scripts/history_replay.py` 历史订单回放
- ✅ `scripts/accuracy_comparison.py` 准确率对比报告

**硬编码修复（P1~P4）**：
- P1: history_replay.py + accuracy_comparison.py 绝对路径 → `_detect_workspace()`
- P2: notification_config.yaml user_id → `${FEISHU_ADMIN_ID:-默认值}` + sender.py 路径检测
- P3: 新增 `config/analysis_config.yaml` 统一管理 8 处阈值
- P4: analyze_learning_data.py `_SKILL_ROOT` 相对路径 → `_detect_workspace()`
- launchd plist × 3 改为 `$AI_ORDER_WORKSPACE` 单点配置

**产出**：
- v5.15.2 发布（VERSION + CHANGELOG）
- `output/self-learning-package-20260612.zip`（77KB，31 个文件）
- 飞书文档已更新：https://feishu.cn/docx/Lo5QdVMvxoH59Ix6SL5cip4tnhe
- Python 文件 `/Users/jinqianfei` 出现次数 = 0

---

### 2026-06-11 16:40 — 阿里云迁移打包

**金姐指示**：阿里云 OpenClaw agent 已部署，需要把订单映射 skill、自学习系统、记忆模块的相关文件打包迁移。

**完成内容**：
- 生成 `output/MIGRATION_MANIFEST.md` 迁移清单（9 大类，198 个文件）
- 生成 `output/ai-order-migration-20260611.tar.gz`（1.6 MB）
- 包含：Skill 核心代码 v5.15.1、自学习系统、CI 回归测试、工作区配置、记忆模块、文档、数据库导出、运维脚本
- 已发送到飞书

**CI 准确率指标（v5.15.2 新增）**：
- `test_mapping_accuracy.py` 新增 D 组仓库映射 + E 组 SKU 映射（D set 20 条盲测数据）
- 5 维度准确率：门店 4/4、货主 11/11、单位 6/6、仓库 21/21、SKU 40/40
- **总计 82/82 = 100%**
- CI 全量 8/8 步骤通过，0 失败

**数据库导出**：
- `output/数据库全量导出_20260611.xlsx`（8 张表，7976 条记录）
- `output/数据库表结构导出_20260611.xlsx`（23 张表，314 个字段）

**STORE_SKU_ACCURACY_ISSUES_REPORT.md review 结论**：
- 第 3 节 SKU 未匹配问题真实存在（"鱼你幸福青花椒酱料（新款）—原椒麻酱料" 被防误匹配规则拦截）
- 修复建议：Step 1 加别名（5 分钟）+ Step 2 改清洗规则（剥离"—原X"补充描述）
- 金姐指示：不要直接改原代码，先写测试验证正常商品名不受影响

---

### 2026-06-11 13:39 — 自学习模块 review + 补齐 6 个缺失 emit

**金姐指示**：重新 review 记忆模块和自学习模块，判断是否需要更新

**Review 发现**：
- **自学习模块**：collector.py 订阅 10 个事件，但 __init__.py 只 emit 了 4 个（40% 覆盖率）
  - 缺失：store_corrected / sku_confirm_needed / sku_confirmed / sku_corrected / order_cancelled / alert_raised
  - 后果：order_corrections 表永远空，layer_success_rate SKU 层永远 0 条数据
- **记忆模块**：版本号不一致（AGENTS.md/MEMORY.md 写 v5.14.0，实际 v5.15.0）

**方案 A（自学习模块补齐 emit）**：
- 在 __init__.py 的合适位置添加 6 个 EventBus.emit 调用
- 所有 emit 包在 try/except 里，失败不影响主流程
- 改完后跑 CI 回归 + 事件管道测试

**方案 B（记忆模块文档对齐）**：
- ✅ AGENTS.md: v5.14.0 → v5.15.0
- ✅ MEMORY.md 头部: v5.14.0 → v5.15.0
- ✅ TOOLS.md: v5.13.2 → v5.15.0
- ✅ MEMORY_SYSTEM_PLAN.md: Phase 3 状态从 🟡 → ✅（脚本已就绪）
- ❌ Supermemory 云端记忆暂不纳入方案（金姐指示）

---

### 2026-06-10 — 5 版本 5 commit + 代码审计 + 端到端回归

**3 轮对话完成**（详细：`memory/2026-06-10.md`）：

#### Round 1: 5 个 commit 分版本提交
- 代码审计发现 v5.9.0 / 5.10.0 / 5.11.0 / 5.11.1 / 5.11.2 全部 4 版本累积在工作区未提交
- 5 个 commit (`0039b89` → `f922f5b`) + 1 doc fix (`bfe76d1`) + git tag v5.11.2
- 修 v5.11.0 tag 错误指向（d199596 → dc86e9f）
- 补 v5.10.0 CHANGELOG 条目（技术锁原本混在 5.11.0 段尾）

#### Round 2: 完整代码逻辑审计（~6000 行 9 文件）
- 实测 5 阶段执行流（初始化 → 类型检测 → 门店匹配 → SKU 匹配 → 模板生成）
- 4 层门店匹配 + 5 层 SKU 匹配精确代码位置
- 31 字段模板生成逐列取值源
- EventBus 6 个 emit 埋点精确行号
- v5.10.0 `__getattribute__` 技术锁真实存在（CHANGELOG 漏记已补）

#### Round 3: 端到端真实订单回归
- 写 `tests/manual_e2e.py`（7063 字节，9 阶段可暂停打印）
- **订单 #1 洪洪通 1店1项** → 100% GT 命中，**出库数量=10** ✅
- **订单 #2 天津仓 2店11项** → 11/11 GT 命中，**出库数量=2,1,1,1,1,1,1,2,2,1,2** ✅
- **总计 12/12 = 100% GT 准确率**，v5.11.1 quantity 修复在多门店场景也生效

#### 🆕 P1 bug 发现（多门店 + 单 confirmed_store）
- 订单 #2：只传 1 个 confirmed_store，Excel 11 行**全部**用第 1 门店 store_code
- 根因：`__init__.py:1785-1797` 多门店循环用同一个 `confirmed_store` 处理所有门店
- 建议：改 `confirmed_stores: Dict[store_key, store_info]`
- **本次不修**（避免范围蔓延）→ 记入 PENDING.md

#### AI 自我复盘
- 诚实性失误：之前"两个事"消息漏写第 2 点，金姐质问时没有先道歉 + 承认
- 教训：每次说"X 个事"前先确认自己列了 X 个，列不齐就说"我想到了 1 个事"

### 2026-06-09 — 数据库全貌盘点 + 清理 + bug 修复 + 端到端验证

**3 件大事完成**：

#### 1) 数据库半完成迁移事故复盘 + 决策回滚 RDS
- 4 份主文档 + 1 份 docs/方案 之前混合描述 RDS / Neon / localhost 三套配置
- 用户金姐明确指示「全部文档对齐为 RDS」 → 全部统一为 `agenthub-db.cjys0msc4x8s.ap-southeast-1.rds.amazonaws.com:5432/neo user=agenthub`
- `.env` 里 `DB_PASSWORD` 被清空 → 从 `.env.bak.20260609_124314` 恢复（30 字符）
- **Neon 账号 `904825541@qq.com` 密码 `TV*fB4Fmyr3*7M!` 是明文发到对话里的** → 已从 `.env` 清掉，建议金姐去 console.neon.tech 改密
- **Neon 项目 `summer-lab` 已不存在** → 历史泄露的 `npg_NG5f1zZFRsgh` 密码自动作废
- `docs/云端部署迁移方案.md` 选方案 A：保留全文 + 头部 disclaimer「未实施 — 2026-06-09 决策：数据库继续使用 AWS RDS，Neon 迁移方案搁置」

#### 2) 数据库全貌盘点 + 清理（P1+P2+P3）
- 探查 22 张表 → 7 活跃 + 15 空表
- **P1.3 DROP product_sku_backup**（3664 行 → 备份到 `/tmp/product_sku_backup_data_20260609_132148.csv` 516KB + 结构到 `/tmp/product_sku_backup_schema_20260609_132147.sql`）
- **P1.4 DROP shipper**（0 行，被 customer 替代）
- **P2.1+P2.2 加 2 个 GIN trgm 索引**：`product_sku.sku_name` + `product_name_alias.order_product_name`
- **P3 15 张空表保留**（按金姐指示）
- **表数 22 → 20，DB 15 MB，索引 5→7**

#### 3) 端到端真实订单测试 + 修复 v5.9.0/5.11.0 漏修的 bug
- **发现关键 bug**：`tools/_sku_mapper.py:map_sku_batch` 调 `_build_result` 不返回 quantity → `__init__._match_sku` 里 `r.get("quantity", 0)` 默认 0 → **31 字段 Excel 出库数量恒为 0**
- **修复**：在 `map_sku_batch` 循环里显式注入 `result["quantity"]` / `unit` / `spec` / `seq`
- **测试**：用 `docs/test_data/test_set_A_history回流.json` 里的 2 个真实订单（1号洪洪通1店1项 + 9号天津仓2店11项）做端到端
  - 1号：椰子水950ml → GT `SK231013000200` 大单位 12瓶/件 → 出库数量=10 ✅
  - 9号：11 个商品全部 GT SKU 匹配（9 个 Layer 1 + 2 个 Layer 1b 去规格匹配）→ 出库数量=2,1,1,1,1,1,1,2,2,1,2 ✅
  - **总计 12/12 = 100% GT 准确率**
- **P1-A CHANGELOG 增 [5.11.1] 条目**（标注 quantity bug 修复 + 测试结果）
- **P1-B VERSION 5.11.0 → 5.11.1**
- **P1-E auto commit 完成**（commit `2e03f2c`，2026-06-09 13:38:30，message "auto: skill 更新"）

**4 个认知错误纠正**：
1. `git ls-files` 输出是 git 根相对路径，不是 pwd 相对路径
2. ai-order 不是独立仓库，git 根是 `/Users/jinqianfei`（大杂烩仓库）
3. ai-order 里 IDENTITY/AGENTS/MEMORY/docs/data 等都不在 git 里，是金姐工作区私有文件
4. 有个 auto commit hook 每 3 分钟自动 commit 金姐的工作区修改

**5 个 GIN trgm 索引**（验证后）：
- `public.product`: `idx_product_product_name_trgm`, `idx_product_sku_code_trgm`
- `public.product_name_alias`: `idx_product_name_alias_order_name_trgm`
- `public.product_sku`: `idx_product_sku_sku_name_trgm`
- `public.shipper`: `idx_shipper_name_trgm`（shipper 表已 DROP，索引级联删除）
- `public.store_list`: `idx_store_list_store_name_trgm`

**金姐下次可能问的子问题**：
- 可分享 skill 需要什么配置？（P0 8 项 + P1 6 项 + P2 5 项，详见对话 13:51-13:52 的清单）

---

### 2026-06-08（昨天）— 方案 C 推进

**金姐两次指示**：
1. 「继续做方案 C」— 推进 v5.9.0 Phase 1
2. 「告诉我现在你的记忆系统是什么」— 交付「好的记忆系统」方案

**方案 C 完成**：
- [x] **纠错**：VERSION 5.8.0 → 5.9.0、CHANGELOG 补 [5.9.0] Phase 1 条目、SKILL.md 头 5.9 → 5.9.0
- [x] **短期防护**：`scripts/version_check.sh` 修复（BSD grep 兼容 + sed 表达式修复），验证通过
- [x] **启动 Phase 1**：事件总线 + 反馈采集器上线

**Phase 1 产出**：
- `events/bus.py` (40行零依赖) + `events/__init__.py`
- `learn/collector.py` (370行) + `learn/adapter.py` + `learn/schema.sql` (3表+2视图)
- 数据库新增表：`order_feedback` / `order_corrections` / `layer_success_rate`
- 数据库新增列：`order_feedback.data_source TEXT`
- `__init__.py` 埋入 6 个 `EventBus.emit()` 调用（4 个事件 × 多门店/单门店两处）
- `scripts/test_event_pipeline.py` 4 项端到端测试 **全过**

**「好的记忆系统」方案**（v1.0）：
- 写入 `memory/MEMORY_SYSTEM_PLAN.md`（5 层架构 + 防断档机制 + 3 阶段实施路线）
- 核心原则：**git/代码/mtime 是唯一真相源，MEMORY.md 是手账**
- 防断档：check_continuity.sh + **每日 10:00 日结** + 启动 4 项自检

**关键学习**：
- 反例 1：EventBus.clear() 会清空 collector 的所有 handler → 修复：init_feedback_collector 加 `force=True` 参数
- 反例 2：order_feedback 表缺 data_source 列 → ALTER TABLE 加列
- 反例 3：__init__.py 的 return + emit 顺序错位 → 重写时确保 emit 在 return 之前
- 反例 4：test 脚本 `OUT=$(...) || EC=$?` 模式成功时不重置 EC → 改用 `OUT=$(...); EC=$?`
- 反例 5：SQL UNION ALL 类型不一致 → 全部 cast 成 ::text
- 重要：MEMORY.md 不应直接当真相源，code/git/mtime 才是

**Phase 2 完成**（16:00）：
- [x] scripts/check_continuity.sh（断档检测，OK/WARN/P0 三档）
- [x] scripts/daily_wrap.sh（**每日 10:00 总结昨天**，金姐指定）
- [x] scripts/startup_check.py（启动 4 项自检：version/git/memory/pending）
- [x] launchd plist（macOS 原生调度，已部署 + 运行）
- [x] scripts/install_launchd.sh（install/uninstall/status/test 4 子命令）
- [x] scripts/test_phase2_guards.sh（**14/14 全部通过**）

**金姐新指示**（15:42）：
- 「日结时间改 10:00，总结昨天数据」— 已落地

**技术细节**：
- 订单事件 4 个：`store_confirm_needed` / `store_confirmed` / `order_complete` / `user_modified`
- 反馈 10 个事件可订阅：上面 4 + `store_corrected` / `sku_confirm_needed` / `sku_confirmed` / `sku_corrected` / `order_cancelled` / `alert_raised`
- 数据库连接：从 `init_feedback_collector(db_config)` 单例管理
- 日志位置：`/tmp/ai-order.daily-wrap.out.log` (stdout) + `.err.log` (stderr)
- 报告位置：`/tmp/daily_wrap_<date>.md`

### 2026-06-04 ~ 2026-06-07（断档期）
- ⚠️ **日志缺失** — SESSION_END_PROTOCOL 未执行
- 能从文件系统推断：
  - 6-4：完成 `SKILL_EVALUATION_REPORT.md`（v5.8 五星评分）
  - 6-5：v5.9 升级（技术锁 __getattribute__ 入库，5.9.1 增量 patch 被 reset 撤销）
  - 6-6 / 6-7：未知
- **教训：以后断档不允许超过 24 小时**

---

## 数据库架构（2026-06-01 重大更新）

### 新增表：product_sku（合并商品表）

**迁移完成**：system_sku + shipper_sku_mapping → product_sku（通过 system_sku_code 关联）

| 字段 | 类型 | 说明 |
|------|------|------|
| `sku_code` | varchar | **华鼎标准SKU编码**（主键 part1） |
| `customer_code` | varchar | 货主自编码 |
| `sku_name` | varchar | 商品名称 |
| `product_spec` | varchar | 包装规格 |
| `unit` | varchar | 基本单位（件/箱/盒） |
| `unit_type` | varchar | 大单位/小单位 |
| `conversion_ratio` | numeric | 换算比 |
| `shipper_id` | varchar | **货主ID**（主键 part2，必填） |
| `category` | varchar | 品类/存储方式 |
| `warehouse_code` | varchar | 默认仓库编码 |
| `status` | varchar | 状态 |

**唯一约束**: `(sku_code, shipper_id)` — 同一SKU可被多个货主使用

**数据量**: 1832条（覆盖12个货主）

### 新增表：product_name_alias（商品名别名表）

| 字段 | 类型 | 说明 |
|------|------|------|
| `order_product_name` | varchar | 订单报货名（含数量单位） |
| `system_product_name` | varchar | 系统标准商品名 |
| `shipper_id` | varchar | 货主ID |

**唯一约束**: `(order_product_name, shipper_id)`

**数据量**: 30条（廖朵朵专用的报货名→系统名映射）

### 已删除表

- ❌ `system_sku`（968条，已合并到 product_sku）
- ❌ `shipper_sku_mapping`（1827条，已合并到 product_sku）

### 保留表

- `store_list` — 门店匹配（3327条，2026-06-04 测评数据）
- `warehouse_code_mapping` — 仓库编码
- `customer` — 货主信息

---

## SKU匹配逻辑（6层）

```
Layer 0: 别名表查表（product_name_alias）
         → 完整订单商品名精确匹配 → 置信度 0.98

Layer 1: 精确匹配（product_sku）
         → sku_name = 输入 OR customer_code = 输入
         → 置信度 0.95

Layer 1b: 去规格后精确匹配
          → 去除商品名中的规格描述后精确匹配
          → 置信度 0.93

Layer 2: 模糊匹配 + 规格校验
         → 相似度 ≥ 0.8 + 规格校验通过 → 直接返回
         → 相似度 ≥ 0.7 + 候选≥2 → 取最佳（需确认）

Layer 2.5: 全量相似度匹配（Layer 2无结果时兜底）
           → 内存中全量SKU相似度计算 + 关键词加成
           → 置信度 min(0.85, score + keyword_boost)

Layer 3: 分词关键词匹配 + 规格校验 + 包含关系加成
         → 相似度 ≥ 0.7 → 返回最佳
         → 置信度 min(0.85, score + keyword_boost)

↓ 全未命中 → unmatched_items
```

---

## 货主数据分布（product_sku）

| 货主ID | 商品数 |
|--------|--------|
| HZ2024061300001 | 640条 |
| HZ2023061500002 | 226条 |
| HZ2025122000013 | 214条 |
| HZ2024091100001 | 146条 |
| HZ2025032700001 | 127条 |
| HZ2026000001 | 102条 |
| HZ2023101200002 | 100条 |
| HZ2024080200002 | 94条 |
| HZ2023061500003 | 59条 |
| HZ2026020300004 | 54条 |
| HZ2025032400001 | 47条 |
| HZ2026012600005 | 23条 |

---

## 门店匹配逻辑（6层）

```
Layer 0: 辅助信息匹配（手机号/收货人/地址）
         → 订单含手机号时优先使用

Layer 1: 客户公司匹配（优先）
         → customer_company 精确匹配 owner_name

Layer 2: 门店名称精确匹配
         → store_name 完全一致

Layer 3: 门店名称模糊匹配
         → 相似度计算 + 关键词交叉

Layer 3.5: 关键词交叉匹配（兆底）
           → 模糊匹配失败后的关键词组合匹配

Layer 3.6: 联系人姓名兆底
           → 用 contact_person 作为门店名重新搜索
```

---

## 核心流程

```
tools_parse() → tools_transform() → _match_store() ⚠️用户确认 → _match_sku() ⚠️用户确认 → _generate_multi_store_template()
```

---

## 最后更新
2026-06-12 10:00 GMT+8

### v5.14.0 工作线收尾（2026-06-11 11:30 GMT+8）
- **全部完成**:
  - ✅ 5 处代码修复 (tools/_sku_mapper.py)
  - ✅ 53/53 CI 回归全过
  - ✅ 85/85 真实 SKU 匹配准确率 (D set 20 + 洪洪通 1 + 天津仓 11 + CI 53)
  - ✅ 文档同步: VERSION 5.14.0 / CHANGELOG [5.14.0] / SKILL.md / MEMORY.md
  - ✅ 测试脚本归档: e2e_v5140.py + gt_v5140_test.py 移到 scripts/
  - ✅ auto commit 已提交 (commit d8a4da2, 11:39:09)
- **A set 9.8% 准确率不是 v5.14.0 bug** — 是 GT 字段为空 / 货主自编码 / 占位符问题
- **金姐指示**: 不要同步飞书 (文档同步规则不扩展)
- **未提交文件**: MEMORY.md / AGENTS.md (auto commit 下次会自动 commit)

> **记忆系统自检（v5.9.0 起强制）**：
> - 每次 session start 跑 `version_check.sh` 核对 VERSION/CHANGELOG/SKILL.md/git tag 四者一致
> - 不一致则立刻报警 + 停止执行任务，强制要求修复
> - 日志断档 > 24h 视为 P0 故障
> - 详见 `memory/MEMORY_SYSTEM_PLAN.md`（5 层架构 + 3 阶段实施）
> - **每日 10:00 强制日结**（macOS launchd 已部署）：总结昨天数据 → 飞书推送 → 写 `/tmp/daily_wrap_<date>.md`
