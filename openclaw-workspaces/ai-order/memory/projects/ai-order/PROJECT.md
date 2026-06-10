# 项目：AI建单助手

**项目名：** ai-order
**老板：** 金姐（金倩妃）
**创建日期：** 2026-05
**最后更新：** 2026-06-10

---

## 项目目标

将客户订单（Excel/图片/PDF/文字/Word）转换为华鼎出库单模板（31 字段），全流程自动化 + 人工关键节点确认。

---

## 当前活跃版本

**Skill：** skill_order_to_huading_template **v5.13.2** (tag `v5.13.2`, 2026-06-10)

- 事件总线 + 反馈采集器 (v5.9.0) — 6 个 emit 埋点运行中
- LLM Provider 配置化 (v5.11.0) — 4 种 provider + 故障回退链
- 硬编码清理 (v5.11.1) — quantity 透传 bug 已修复
- 配置统一化 (v5.11.2) — 31 字段 yaml + 表名常量
- 数据库：localhost:5432/neo（jinqianfei）
- git tag: v5.9.0-baseline / v5.11.0 / v5.11.2 三个里程碑

---

## 项目结构

```
ai-order/
├── AGENTS.md              ← Agent 工作区说明
├── IDENTITY.md            ← 身份配置
├── SOUL.md                ← 性格与风格
├── TOOLS.md               ← 工具说明
├── USER.md                ← 老板信息
├── MEMORY.md              ← 记忆摘要（真相源：VERSION + git log）
├── HEARTBEAT.md           ← 周期性任务
├── SKILL_EVALUATION_REPORT.md  ← v5.8 五星测评报告
├── 重构方案_skill_order_to_huading_template.md  ← 5 阶段重构路线
│
├── skills/
│   └── skill_order_to_huading_template/    ← 唯一活跃 skill
│       ├── SKILL.md                        ← 流程文档
│       ├── VERSION                         ← "5.9.0"
│       ├── CHANGELOG.md                    ← 版本变更日志
│       ├── __init__.py                     ← 主入口（技术锁 + 6 个 EventBus.emit）
│       ├── tools/                          ← 解析/匹配/生成工具
│       ├── db/                             ← 数据库层
│       ├── field_mapping/                  ← 字段映射规则库
│       ├── events/                         ← 🆕 事件总线 (Phase 1)
│       │   ├── __init__.py
│       │   └── bus.py
│       ├── learn/                          ← 🆕 反馈采集器 (Phase 1)
│       │   ├── __init__.py
│       │   ├── collector.py
│       │   ├── adapter.py
│       │   ├── schema.sql                   ← 已执行
│       │   ├── ADAPTIVE_LEARNING_METHOD_B.md
│       │   └── README.md
│       └── scripts/
│           ├── version_check.sh            ← 🆕 启动时版本号自检
│           └── test_event_pipeline.py      ← 🆕 4 项端到端测试
│
├── memory/                                 ← 记忆系统
│   ├── 2026-06-08.md                       ← 今日 session 日志
│   ├── 2026-06-04-to-07.md                 ← 断档期追溯
│   ├── MEMORY_SYSTEM_PLAN.md               ← 🆕 「好的记忆系统」方案 v1.0
│   ├── SESSION_START_PROTOCOL.md
│   ├── SESSION_END_PROTOCOL.md
│   ├── PENDING_PROTOCOL.md
│   └── projects/ai-order/
│       ├── PROJECT.md                      ← 🆕 本文件
│       └── problems/PENDING.md             ← 🆕 未完成事项
│
└── database/, docs/, excel/, backups/, output/
```

---

## 核心流程

```
客户订单（Excel/图片/PDF/文字/Word）
    ↓
Step 1: order_parser.parse()       ← LLM 解析
    ↓
Step 2: field_transformer.transform()  ← 规则库标准化
    ↓
Step 3: _match_store()             ← ⚠️ 用户确认门店
    ↓
Step 4: _match_sku()              ← ⚠️ 用户确认 SKU
    ↓
Step 5: _generate_multi_store_template()  ← 生成 31 字段 Excel
    ↓
[Phase 1] EventBus.emit × 6       ← 反馈采集（已埋点）
    ↓
order_feedback 表                  ← 自适应学习数据
```

---

## 关键决策记录

### 2026-06-08：方案 C 落地
- **触发**：金姐问"怎么才能做到一个好的记忆"
- **决定**：方案 C（纠错 + 短期防护 + 启动 Phase 1）+ 写「好的记忆系统」方案
- **理由**：短期能止血、长期能自治
- **证据**：`memory/MEMORY_SYSTEM_PLAN.md` + version_check.sh + 4 项测试

### 2026-06-05：v5.9.0 技术锁
- **触发**：AI 调用可能绕过 `execute()` 主入口
- **决定**：用 `__getattribute__` 拦截
- **理由**：技术层面强制 AI 必须用主入口
- **反例**：`__getattribute__` 对模块级函数无影响（EventBus 不受影响）

### 2026-06-01：数据库合并
- **决定**：`system_sku` + `shipper_sku_mapping` → `product_sku`
- **理由**：减少 JOIN，提升匹配速度
- **数据**：1832 条 SKU，12 个货主

---

## 联系方式

- 老板：飞书 / 电话（`memory/credentials/INDEX.md`）
- 紧急事项：飞书消息
