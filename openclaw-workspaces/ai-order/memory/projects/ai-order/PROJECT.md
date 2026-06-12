# 项目：AI建单助手

**项目名：** ai-order
**老板：** 金姐（金倩菲）
**创建日期：** 2026-05
**最后更新：** 2026-06-12

---

## 项目目标

将客户订单（Excel/图片/PDF/文字/Word）转换为华鼎出库单模板（31 字段），全流程自动化 + 人工关键节点确认。

---

## 当前活跃版本

**Skill：** skill_order_to_huading_template **v5.15.2** (2026-06-12)

- 事件总线 + 反馈采集器 (v5.9.0) — 10 个 emit 埋点 100% 覆盖
- LLM Provider 配置化 (v5.11.0) — 4 种 provider + 故障回退链
- 硬编码清理 (v5.11.1) — quantity 透传 bug 已修复
- 配置统一化 (v5.11.2) — 31 字段 yaml + 表名常量
- 果糖末尾分隔符修复 (v5.13.3) — _clean_product_name 锚点正则
- 单位匹配逻辑 (v5.14.0) — _compute_match_score + _select_unique_best
- 自学习补齐 (v5.15.0~v5.15.1) — 6 个缺失 emit + 文档对齐
- store_corrected 误触发修复 (v5.15.2) — 多门店对比逻辑
- 硬编码全修 (v5.15.2) — P1~P4 + launchd plist + analysis_config.yaml
- 数据库：AWS RDS PostgreSQL (agenthub-db.cjys0msc4x8s.ap-southeast-1.rds.amazonaws.com:5432/neo)
- git tag: v5.9.0-baseline / v5.11.0 / v5.11.2 / v5.12.0 四个里程碑

---

## 项目结构

```
ai-order/
├── AGENTS.md              ← Agent 工作区说明
├── IDENTITY.md            ← 身份配置（货主-品牌对照 + 数据库架构）
├── SOUL.md                ← 性格与风格
├── TOOLS.md               ← 工具说明（数据库配置 + 钉钉 CLI）
├── USER.md                ← 老板信息
├── MEMORY.md              ← 记忆摘要（真相源：VERSION + git log）
├── HEARTBEAT.md           ← 周期性任务
├── SKILL_EVALUATION_REPORT.md  ← v5.8 五星测评报告
├── 重构方案_skill_order_to_huading_template.md  ← 5 阶段重构路线
│
├── skills/
│   └── skill_order_to_huading_template/    ← 唯一活跃 skill (v5.15.2)
│       ├── SKILL.md                        ← 流程文档
│       ├── VERSION                         ← "5.15.2"
│       ├── CHANGELOG.md                    ← 版本变更日志
│       ├── __init__.py                     ← 主入口（技术锁 + 10 个 EventBus.emit）
│       ├── tools/                          ← 解析/匹配/生成工具
│       │   ├── __init__.py
│       │   ├── _order_parser.py            ← LLM 订单解析
│       │   ├── _field_transformer.py       ← 规则库标准化
│       │   ├── _store_matcher.py           ← 门店匹配（6层）
│       │   ├── _sku_mapper.py              ← SKU 映射（6层 + 单位打分）
│       │   └── _template_generator.py      ← 31 字段模板生成
│       ├── db/                             ← 数据库层
│       │   ├── __init__.py
│       │   ├── connection.py               ← psycopg2 连接池
│       │   ├── customer_repo.py            ← 货主数据
│       │   ├── sku_repo.py                 ← SKU 数据
│       │   ├── store_repo.py               ← 门店数据
│       │   └── table_names.py              ← 表名常量
│       ├── field_mapping/                  ← 字段映射规则库
│       │   ├── __init__.py
│       │   ├── transformer.py
│       │   ├── schemas/__init__.py
│       │   └── rules/
│       │       ├── default.yaml
│       │       ├── field_aliases_auto.yaml
│       │       ├── sku_aliases_auto.yaml
│       │       ├── 创宇.yaml
│       │       ├── 小江溪.yaml
│       │       └── 王小五.yaml
│       ├── events/                         ← 事件总线 (Phase 1)
│       │   ├── __init__.py
│       │   └── bus.py                      ← 零依赖事件总线
│       ├── learn/                          ← 自学习模块 (Phase 1~3)
│       │   ├── __init__.py
│       │   ├── collector.py                ← 反馈采集器（10 事件订阅）
│       │   ├── adapter.py                  ← 数据适配
│       │   ├── schema.sql                  ← 3 表 + 2 视图
│       │   ├── README.md
│       │   ├── ADAPTIVE_LEARNING_METHOD_B.md
│       │   └── llm/                        ← LLM Provider 配置化
│       │       ├── __init__.py
│       │       ├── provider.py             ← 抽象 Provider
│       │       ├── router.py               ← 故障回退链
│       │       ├── openai.py               ← OpenAI Provider
│       │       ├── openai_compat.py        ← OpenAI 兼容
│       │       ├── openclaw.py             ← OpenClaw Provider
│       │       └── custom_http.py          ← 自定义 HTTP
│       ├── config/                         ← 配置文件
│       │   ├── __init__.py
│       │   ├── db_config.yaml              ← 数据库连接
│       │   ├── llm.yaml                    ← LLM Provider 配置
│       │   └── template_defaults.yaml      ← 31 字段默认值
│       └── scripts/                        ← 测试/运维脚本
│           ├── version_check.sh            ← 版本号 4 处一致性检查
│           ├── ci_regression.sh            ← CI 回归入口
│           ├── test_event_pipeline.py      ← 4 项事件管道测试
│           ├── test_sku_mapper_regression.py ← 45 个 SKU 边界测试
│           ├── test_execute_confirmation_flow.py ← P1 bug 回归
│           ├── test_execute_import_fallback.py   ← import fallback
│           ├── test_mapping_accuracy.py    ← D 组仓库映射 + E 组 SKU 映射
│           ├── test_order_parser_excel_header_detail.py
│           ├── test_order_parser_text_fallback.py
│           ├── e2e_v5140.py                ← v5.14.0 端到端
│           ├── gt_v5140_test.py            ← v5.14.0 GT 比对
│           ├── history_replay.py           ← 历史订单回放
│           ├── accuracy_comparison.py      ← 准确率对比报告
│           ├── accuracy_audit.py           ← 准确率审计
│           ├── inspect_accuracy_failures.py ← 失败用例检查
│           └── sync_check.sh              ← 同步检查
│
├── scripts/                                ← 工作区运维脚本
│   ├── analyze_learning_data.py            ← 自学习数据分析
│   ├── notification_sender.py              ← 飞书通知
│   ├── check_continuity.sh                 ← 断档检测
│   ├── daily_wrap.sh                       ← 每日 10:00 日结
│   ├── startup_check.py                    ← 启动 4 项自检
│   ├── check_memory_quality.py             ← 记忆质量评分
│   ├── extract_memory.py                   ← 记忆提取
│   ├── reindex_memory.py                   ← 记忆重索引
│   ├── daily_alias_summary.py              ← 日别名汇总
│   ├── install_launchd.sh                  ← launchd 部署
│   ├── phase3_maintenance.sh               ← Phase 3 维护
│   ├── test_phase2_guards.sh               ← Phase 2 防护测试
│   ├── test_phase3.sh                      ← Phase 3 测试
│   ├── auto_git_skill.sh                   ← 自动 git
│   ├── deploy_openclaw.sh                  ← 部署
│   ├── setup_agent.sh                      ← 初始化
│   └── sync_to_ec2.sh                      ← EC2 同步
│
├── config/                                 ← 工作区配置
│   ├── analysis_config.yaml                ← 8 处阈值统一管理
│   └── notification_config.yaml            ← 通知配置
│
├── memory/                                 ← 记忆系统
│   ├── 2026-05-28.md                       ← session 日志
│   ├── 2026-06-01.md
│   ├── 2026-06-03.md
│   ├── 2026-06-04-to-07.md                 ← 断档期追溯
│   ├── 2026-06-08.md
│   ├── 2026-06-10.md
│   ├── 2026-06-11.md                       ← 自学习补齐 + CI + v5.14.0
│   ├── 2026-06-12.md                       ← 硬编码修复 + 闭环 review
│   ├── MEMORY_SYSTEM_PLAN.md               ← 记忆系统方案 v1.0（5 层架构）
│   ├── SESSION_START_PROTOCOL.md
│   ├── SESSION_END_PROTOCOL.md
│   ├── PENDING_PROTOCOL.md
│   ├── credentials/                        ← 凭证管理
│   │   └── INDEX.md
│   └── projects/ai-order/
│       ├── PROJECT.md                      ← 本文件
│       └── problems/PENDING.md             ← 未完成事项
│
└── docs/, data/, output/, backups/, excel/
```

---

## 核心流程

```
客户订单（Excel/图片/PDF/文字/Word）
    ↓
Step 1: order_parser.parse()           ← LLM 解析
    ↓
Step 2: field_transformer.transform()  ← 规则库标准化
    ↓
Step 3: _match_store()                 ← ⚠️ 用户确认门店（6层匹配）
    ↓
Step 4: _match_sku()                   ← ⚠️ 用户确认 SKU（6层匹配 + 单位打分）
    ↓
Step 5: _generate_multi_store_template()  ← 生成 31 字段 Excel
    ↓
[自学习] EventBus.emit × 10            ← 反馈采集（10 事件 100% 覆盖）
    ↓
order_feedback / order_corrections 表   ← 自适应学习数据
```

---

## 关键决策记录

### 2026-06-12：硬编码全修 + 阈值配置化
- **触发**：review 工作区发现多处硬编码
- **决定**：P1~P4 全部修复 + launchd plist 单点配置 + config/analysis_config.yaml
- **理由**：提高可维护性，避免路径/阈值散落
- **产出**：`_detect_workspace()` 动态检测 + 8 处阈值统一管理

### 2026-06-12：store_corrected 误触发修复
- **触发**：order_corrections 0 条诊断发现多门店 bug
- **决定**：新增 `_call_match_store` 对比逻辑
- **理由**：用户选的 ≠ 系统匹配时才 emit，避免误触发

### 2026-06-11：单位匹配逻辑重构
- **触发**：金姐反馈"订单 1 件匹配到瓶"
- **决定**：新增 `_compute_match_score()` + `_select_unique_best()`
- **理由**：单位和 SKU 是绑定的，不是单独匹配

### 2026-06-11：CI 回归测试建立
- **触发**：金姐指示"把边界用例固化成单元测试"
- **决定**：53 个测试用例 + ci_regression.sh
- **理由**：防止回归，每次改核心代码必跑

### 2026-06-10：P1 bug 发现 + 修复
- **触发**：端到端测试发现多门店 + 单 confirmed_store 行为错误
- **决定**：v5.12.0 修复 + 4 个 tag 推送
- **理由**：影响多门店订单的 store_code 正确性

### 2026-06-08：方案 C 落地
- **触发**：金姐问"怎么才能做到一个好的记忆"
- **决定**：方案 C（纠错 + 短期防护 + 启动 Phase 1）+ 写记忆系统方案
- **理由**：短期能止血、长期能自治

### 2026-06-05：v5.9.0 技术锁
- **触发**：AI 调用可能绕过 `execute()` 主入口
- **决定**：用 `__getattribute__` 拦截
- **理由**：技术层面强制 AI 必须用主入口

### 2026-06-01：数据库合并
- **决定**：`system_sku` + `shipper_sku_mapping` → `product_sku`
- **理由**：减少 JOIN，提升匹配速度
- **数据**：1832 条 SKU，12 个货主

---

## 自学习模块状态

| Phase | 状态 | 说明 |
|-------|------|------|
| Phase 1 | ✅ | 事件总线 + 反馈采集器（10 事件 100% 覆盖）|
| Phase 2 | ✅ | LLM Provider 配置化（4 provider + 回退链）|
| Phase 3 | ✅ | 分析脚本 + 通知脚本 + 历史回放 |
| Phase 4 | ⏳ | 自适应学习循环（需数据积累）|
| Phase 5 | ⏳ | 全自动优化（长期目标）|

---

## 记忆模块状态

| Phase | 状态 | 说明 |
|-------|------|------|
| Phase 1 | ✅ | 事件总线 + 反馈采集器 |
| Phase 2 | ✅ | 日结脚本 + launchd + 启动自检 |
| Phase 3 | ✅ | 记忆质量检查 + 重索引 + 提取脚本 |
| Phase 4 | ⏳ | 自治（AI 自动执行 session 协议）|

---

## 联系方式

- 老板：飞书 / 电话（`memory/credentials/INDEX.md`）
- 紧急事项：飞书消息
