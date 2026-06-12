# AI建单助手 — 模块拆分方案

> ⚠️ **本文档已废弃** — 请使用 `docs/REFACTOR_PLAN_COMPLETE.md`
>
> 废弃原因：本方案过度工程化（infrastructure/ 通用层过早抽象），且未解决 `__init__.py` 4153行的核心技术债
>
> **版本**：v1.0 | **日期**：2026-06-12 | **作者**：AI建单助手 + 金姐

---

## 1. 背景

### 1.1 当前问题

AI建单助手工作区目前把三大职责耦合在同一个目录下：

| 职责 | 代码位置 | 行数估算 |
|------|---------|---------|
| 订单映射 Skill | `skills/skill_order_to_huading_template/` | ~6000 行 |
| 自学习模块 | `skills/.../learn/` + `scripts/` + `config/` + `launchd/` | ~1500 行 |
| 记忆模块 | `memory/` + `scripts/` + Supermemory 云端 | ~800 行 |

**耦合带来的问题**：
1. **复用困难** — 自学习和记忆是通用能力，但绑死在 ai-order 项目里，AI 客服、供应链计划等新项目无法复用
2. **部署耦合** — 迁移到阿里云时需要把整个 ai-order 打包（1.6MB），实际只需要 Skill 核心
3. **职责模糊** — `scripts/` 下混放了自学习脚本、记忆脚本、运维脚本，新人接手困难
4. **测试困难** — 改自学习逻辑可能意外影响订单处理流程

### 1.2 拆分目标

```
✅ 三个模块各自独立：可单独部署、单独测试、单独复用
✅ 订单映射 Skill 保持纯净：只做订单处理，不关心学习和记忆
✅ 自学习框架通用化：任何 Skill 都能接入
✅ 记忆系统统一化：一套协议服务所有 Agent
✅ 向后兼容：拆分期间不影响现有订单处理
```

---

## 2. 当前架构全景

```
ai-order/
├── skills/skill_order_to_huading_template/     # 订单映射 Skill (v5.15.4)
│   ├── __init__.py          (4153行 — 主入口 + EventBus emit)
│   ├── tools/               (5个工具文件)
│   │   ├── _order_parser.py
│   │   ├── _field_transformer.py
│   │   ├── _store_matcher.py
│   │   ├── _sku_mapper.py
│   │   └── _template_generator.py
│   ├── config/              (Skill 配置)
│   │   ├── db_config.yaml
│   │   ├── llm.yaml
│   │   └── template_defaults.yaml
│   ├── events/              (EventBus — 事件总线)
│   │   ├── bus.py
│   │   └── __init__.py
│   ├── db/                  (数据库连接)
│   │   └── connection.py
│   ├── learn/               (自学习 Phase 1)  ← 【要拆分】
│   │   ├── collector.py     (事件订阅 + 数据写入)
│   │   ├── adapter.py       (payload 转换)
│   │   ├── schema.sql       (建表 SQL)
│   │   └── llm/             (LLM Provider)
│   │       ├── router.py
│   │       ├── provider.py
│   │       ├── openai.py
│   │       ├── openai_compat.py
│   │       ├── openclaw.py
│   │       └── custom_http.py
│   └── tests/               (Skill 测试)
│       └── test_p1_multi_store_fix.py
│
├── scripts/                 ← 【混杂，要拆分】
│   ├── analyze_learning_data.py    (自学习分析)
│   ├── daily_alias_summary.py      (自学习-别名汇总)
│   ├── notification_sender.py      (自学习-通知)
│   ├── check_memory_quality.py     (记忆-质量检查)
│   ├── extract_memory.py           (记忆-提取)
│   ├── reindex_memory.py           (记忆-索引)
│   ├── startup_check.py            (记忆+Skill-启动检查)
│   ├── daily_wrap.sh               (运维-日结)
│   ├── check_continuity.sh         (运维-断档检测)
│   ├── auto_git_skill.sh           (运维-Git)
│   ├── deploy_to_aliyun.sh         (运维-部署)
│   ├── sync_to_aliyun.sh           (运维-同步)
│   ├── sync_to_ec2.sh              (运维-同步)
│   ├── setup_agent.sh              (运维-初始化)
│   ├── install_launchd.sh          (运维-launchd)
│   ├── export_db_for_migration.py  (运维-DB导出)
│   ├── run_migrations.sh           (运维-迁移)
│   └── weekly_archive.sh           (运维-周归档)
│
├── config/                  ← 【要拆分】
│   ├── analysis_config.yaml        (自学习分析阈值)
│   └── notification_config.yaml    (通知配置)
│
├── launchd/                 ← 【要拆分】
│   ├── com.ai-order.daily-wrap.plist
│   ├── com.ai-order.daily-alias-summary.plist
│   └── com.ai-order.phase3-maintenance.plist
│
├── memory/                  ← 【要拆分】
│   ├── SESSION_START_PROTOCOL.md
│   ├── SESSION_END_PROTOCOL.md
│   ├── MEMORY_SYSTEM_PLAN.md
│   ├── PENDING_PROTOCOL.md
│   ├── projects/
│   │   ├── PROJECT_TEMPLATE.md
│   │   └── ai-order/
│   └── archive/
│
├── docs/                    (文档)
├── data/                    (测试数据)
├── output/                  (输出文件)
├── AGENTS.md / SOUL.md / IDENTITY.md / USER.md / TOOLS.md / MEMORY.md
└── .env / .env.bak.*
```

---

## 3. 目标架构

### 3.1 目录结构

```
ai-order/                                    # 订单项目（轻量壳）
├── AGENTS.md / SOUL.md / ...               # Agent 配置（保留）
├── .env                                     # 环境变量（保留）
│
├── skills/
│   └── skill_order_to_huading_template/     # 纯订单处理 Skill
│       ├── __init__.py                      # 主入口（精简，移除学习相关 emit 的硬依赖）
│       ├── tools/                           # 5 个工具（不动）
│       ├── config/                          # Skill 配置（不动）
│       ├── events/                          # EventBus（保留 — 是基础设施）
│       ├── db/                              # 数据库连接（保留）
│       ├── tests/                           # Skill 测试（保留）
│       └── VERSION / CHANGELOG.md / SKILL.md
│
├── infrastructure/                          # 🆕 通用基础设施层
│   ├── self_learning/                       # 自学习框架（通用）
│   │   ├── core/
│   │   │   ├── collector.py                 # 通用事件收集器
│   │   │   ├── adapter.py                   # 通用 payload 适配器
│   │   │   ├── analyzer.py                  # 通用分析引擎
│   │   │   ├── improver.py                  # 通用改进建议生成器
│   │   │   └── schema.sql                   # 通用建表 SQL
│   │   ├── llm/                             # LLM Provider（通用）
│   │   │   ├── router.py
│   │   │   ├── provider.py
│   │   │   ├── openai.py
│   │   │   ├── openai_compat.py
│   │   │   ├── openclaw.py
│   │   │   └── custom_http.py
│   │   ├── config/
│   │   │   ├── analysis_config.yaml         # 分析阈值
│   │   │   └── notification_config.yaml     # 通知配置
│   │   ├── scripts/
│   │   │   ├── analyze_data.py              # 通用分析脚本
│   │   │   ├── daily_summary.py             # 通用日汇总
│   │   │   └── notification_sender.py       # 通用通知
│   │   └── __init__.py
│   │
│   ├── memory_system/                       # 记忆系统（通用）
│   │   ├── protocols/
│   │   │   ├── SESSION_START_PROTOCOL.md
│   │   │   ├── SESSION_END_PROTOCOL.md
│   │   │   └── PENDING_PROTOCOL.md
│   │   ├── scripts/
│   │   │   ├── check_quality.py             # 记忆质量检查
│   │   │   ├── extract_memory.py            # 记忆提取
│   │   │   ├── reindex.py                   # 记忆索引
│   │   │   └── startup_check.py             # 启动自检
│   │   ├── templates/
│   │   │   └── PROJECT_TEMPLATE.md
│   │   └── __init__.py
│   │
│   └── event_bus/                           # EventBus（通用，从 Skill 提取）
│       ├── bus.py
│       └── __init__.py
│
├── integrations/                            # 🆕 业务适配层（胶水代码）
│   └── order_self_learning/                 # 订单专用学习规则
│       ├── order_collector_hooks.py         # 订单事件 → 通用收集器的适配
│       ├── order_analysis_rules.py          # 订单专用分析规则
│       └── __init__.py
│
├── ops/                                     # 🆕 运维脚本（从 scripts/ 迁移）
│   ├── daily_wrap.sh
│   ├── check_continuity.sh
│   ├── auto_git_skill.sh
│   ├── deploy_to_aliyun.sh
│   ├── sync_to_aliyun.sh
│   ├── sync_to_ec2.sh
│   ├── setup_agent.sh
│   ├── install_launchd.sh
│   ├── export_db_for_migration.py
│   ├── run_migrations.sh
│   ├── weekly_archive.sh
│   └── monthly_review.sh
│
├── launchd/                                 # launchd 配置（保留，更新路径）
│   ├── com.ai-order.daily-wrap.plist
│   ├── com.ai-order.daily-alias-summary.plist
│   └── com.ai-order.phase3-maintenance.plist
│
├── memory/                                  # 运行时数据（保留，不迁移）
│   ├── 2026-06-*.md                         # 日志
│   └── projects/ai-order/                   # 项目记忆
│
├── docs/                                    # 文档（保留）
├── data/                                    # 测试数据（保留）
└── output/                                  # 输出文件（保留）
```

### 3.2 依赖关系（拆分后）

```
                    ┌─────────────────────────┐
                    │   ai-order (项目壳)      │
                    │   AGENTS.md / .env       │
                    └───────┬─────────────────┘
                            │ 使用
                            ▼
          ┌─────────────────────────────────────┐
          │  skill_order_to_huading_template    │
          │  (纯订单处理)                        │
          │  tools/ + config/ + db/             │
          └────────┬──────────────┬─────────────┘
                   │ emit 事件     │ 查询记忆
                   ▼              ▼
     ┌──────────────────┐  ┌──────────────────┐
     │  event_bus/       │  │  memory_system/  │
     │  (通用事件总线)    │  │  (通用记忆系统)   │
     └────────┬─────────┘  └──────────────────┘
              │ 订阅
              ▼
     ┌──────────────────┐
     │  self_learning/   │
     │  (通用学习框架)    │
     └────────┬─────────┘
              │ 适配
              ▼
     ┌──────────────────────────┐
     │  integrations/            │
     │  order_self_learning/     │
     │  (订单专用学习规则)        │
     └──────────────────────────┘
```

**核心原则**：
- **上层依赖下层**，下层不知道上层存在
- `event_bus` 是基础设施，谁都能用
- `self_learning` 订阅 `event_bus` 的事件，不直接依赖 Skill
- `integrations/` 是胶水层，把通用框架适配到具体业务

---

## 4. 分步实施计划

### Phase 1：提取 EventBus（最底层，无依赖）

**目标**：把 `events/bus.py` 提取为独立模块

**当前状态**：
```
skills/skill_order_to_huading_template/events/bus.py  (EventBus 类)
```

**目标状态**：
```
infrastructure/event_bus/bus.py     (EventBus 类)
infrastructure/event_bus/__init__.py
```

**文件映射**：

| 源文件 | 目标文件 | 操作 |
|-------|---------|------|
| `skills/.../events/bus.py` | `infrastructure/event_bus/bus.py` | 移动 |
| `skills/.../events/__init__.py` | `infrastructure/event_bus/__init__.py` | 移动 |

**兼容处理**：
```python
# skills/.../events/__init__.py（保留为 shim）
# 向后兼容：旧代码 from events.bus import EventBus 仍可用
from infrastructure.event_bus import EventBus
```

**风险**：低 — EventBus 是无状态单例，移动后只需更新 import 路径

**验证**：
```bash
# 确认 Skill 主入口的 EventBus 引用更新
grep -r "from events" skills/skill_order_to_huading_template/
# 确认所有 emit/on 调用正常
python3 -c "from infrastructure.event_bus import EventBus; print('OK')"
```

---

### Phase 2：提取自学习模块

**目标**：把自学习相关代码从 Skill 和 scripts/ 中拆出来

#### Phase 2a：提取核心框架

**文件映射**：

| 源文件 | 目标文件 | 操作 |
|-------|---------|------|
| `skills/.../learn/collector.py` | `infrastructure/self_learning/core/collector.py` | 移动 + 通用化 |
| `skills/.../learn/adapter.py` | `infrastructure/self_learning/core/adapter.py` | 移动 + 通用化 |
| `skills/.../learn/schema.sql` | `infrastructure/self_learning/core/schema.sql` | 移动 |
| `skills/.../learn/llm/` (整个目录) | `infrastructure/self_learning/llm/` | 移动 |
| `config/analysis_config.yaml` | `infrastructure/self_learning/config/analysis_config.yaml` | 移动 |
| `config/notification_config.yaml` | `infrastructure/self_learning/config/notification_config.yaml` | 移动 |

**通用化改造**：

`collector.py` 的通用化（核心改动）：
```python
# 改造前（订单专用）：
class FeedbackCollector:
    def __init__(self, db_config: dict):
        EventBus.on("store_confirm_needed", self.on_store_confirm_needed)
        EventBus.on("sku_confirmed", self.on_sku_confirmed)
        # ... 硬编码 10 个订单事件

# 改造后（通用框架）：
class LearningCollector:
    def __init__(self, db_config: dict, event_map: dict = None):
        """
        event_map: 事件名 → 处理函数的映射
        如果不传，使用默认的事件映射（由 integration 层注入）
        """
        self._event_map = event_map or self._default_event_map()
        for event_name, handler in self._event_map.items():
            EventBus.on(event_name, handler)
```

#### Phase 2b：迁移分析脚本

| 源文件 | 目标文件 | 操作 |
|-------|---------|------|
| `scripts/analyze_learning_data.py` | `infrastructure/self_learning/scripts/analyze_data.py` | 移动 + 通用化 |
| `scripts/daily_alias_summary.py` | `infrastructure/self_learning/scripts/daily_summary.py` | 移动 + 通用化 |
| `scripts/notification_sender.py` | `infrastructure/self_learning/scripts/notification_sender.py` | 移动 |

#### Phase 2c：创建订单适配层

| 源文件 | 目标文件 | 操作 |
|-------|---------|------|
| 🆕 | `integrations/order_self_learning/order_collector_hooks.py` | 新建 |
| 🆕 | `integrations/order_self_learning/order_analysis_rules.py` | 新建 |
| 🆕 | `integrations/order_self_learning/__init__.py` | 新建 |

`order_collector_hooks.py` 示例：
```python
"""
订单专用学习钩子 — 把订单事件映射到通用 LearningCollector
"""
from infrastructure.self_learning.core import LearningCollector

ORDER_EVENT_MAP = {
    "store_confirm_needed": "on_store_confirm_needed",
    "store_confirmed": "on_store_confirmed",
    "store_corrected": "on_store_corrected",
    "sku_confirm_needed": "on_sku_confirm_needed",
    "sku_confirmed": "on_sku_confirmed",
    "sku_corrected": "on_sku_corrected",
    "order_complete": "on_order_complete",
    "order_cancelled": "on_order_cancelled",
    "user_modified": "on_user_modified",
    "alert_raised": "on_alert_raised",
}

def init_order_learning(db_config: dict) -> LearningCollector:
    return LearningCollector(db_config, event_map=ORDER_EVENT_MAP)
```

---

### Phase 3：提取记忆模块

**目标**：把记忆协议和质量检查工具通用化

**文件映射**：

| 源文件 | 目标文件 | 操作 |
|-------|---------|------|
| `memory/SESSION_START_PROTOCOL.md` | `infrastructure/memory_system/protocols/SESSION_START_PROTOCOL.md` | 移动 |
| `memory/SESSION_END_PROTOCOL.md` | `infrastructure/memory_system/protocols/SESSION_END_PROTOCOL.md` | 移动 |
| `memory/PENDING_PROTOCOL.md` | `infrastructure/memory_system/protocols/PENDING_PROTOCOL.md` | 移动 |
| `memory/projects/PROJECT_TEMPLATE.md` | `infrastructure/memory_system/templates/PROJECT_TEMPLATE.md` | 移动 |
| `scripts/check_memory_quality.py` | `infrastructure/memory_system/scripts/check_quality.py` | 移动 + 通用化 |
| `scripts/extract_memory.py` | `infrastructure/memory_system/scripts/extract_memory.py` | 移动 |
| `scripts/reindex_memory.py` | `infrastructure/memory_system/scripts/reindex.py` | 移动 |
| `scripts/startup_check.py` | `infrastructure/memory_system/scripts/startup_check.py` | 拆分* |

> *`startup_check.py` 同时检查版本（Skill 相关）和记忆新鲜度（记忆相关）。拆分方案：
> - 记忆检查部分 → `infrastructure/memory_system/scripts/startup_check.py`
> - 版本检查部分 → 保留在 Skill 的 `scripts/version_check.sh`（已有）
> - 原 `startup_check.py` 改为调用两部分的组合脚本

**保留在 `memory/` 的运行时数据**（不迁移）：
```
memory/2026-06-*.md              # 日志（运行时产物）
memory/projects/ai-order/        # 项目专属记忆
memory/archive/                  # 归档
```

---

### Phase 4：整理运维脚本

**目标**：把 `scripts/` 下的运维脚本移到 `ops/`

**文件映射**：

| 源文件 | 目标文件 |
|-------|---------|
| `scripts/daily_wrap.sh` | `ops/daily_wrap.sh` |
| `scripts/check_continuity.sh` | `ops/check_continuity.sh` |
| `scripts/auto_git_skill.sh` | `ops/auto_git_skill.sh` |
| `scripts/deploy_to_aliyun.sh` | `ops/deploy_to_aliyun.sh` |
| `scripts/sync_to_aliyun.sh` | `ops/sync_to_aliyun.sh` |
| `scripts/sync_to_ec2.sh` | `ops/sync_to_ec2.sh` |
| `scripts/setup_agent.sh` | `ops/setup_agent.sh` |
| `scripts/install_launchd.sh` | `ops/install_launchd.sh` |
| `scripts/export_db_for_migration.py` | `ops/export_db_for_migration.py` |
| `scripts/run_migrations.sh` | `ops/run_migrations.sh` |
| `scripts/weekly_archive.sh` | `ops/weekly_archive.sh` |
| `scripts/monthly_review.sh` | `ops/monthly_review.sh` |
| `scripts/phase3_maintenance.sh` | `ops/phase3_maintenance.sh` |
| `scripts/test_phase2_guards.sh` | `ops/test_phase2_guards.sh` |
| `scripts/test_phase3.sh` | `ops/test_phase3.sh` |

**保留在 `scripts/` 的**：
- `scripts/ci_regression.sh`（Skill CI 回归测试入口）
- `scripts/test_sku_mapper_regression.py`（Skill 单元测试）
- `scripts/history_replay.py`（自学习集成，移到 integrations/）
- `scripts/accuracy_comparison.py`（自学习集成，移到 integrations/）

---

### Phase 5：更新 launchd + CI

**目标**：更新所有路径引用

#### launchd 配置更新

```xml
<!-- 改造前 -->
<key>ProgramArguments</key>
<array>
    <string>/bin/bash</string>
    <string>/Users/jinqianfei/openclaw-workspaces/ai-order/scripts/daily_wrap.sh</string>
</array>

<!-- 改造后 -->
<key>ProgramArguments</key>
<array>
    <string>/bin/bash</string>
    <string>/Users/jinqianfei/openclaw-workspaces/ai-order/ops/daily_wrap.sh</string>
</array>
```

#### CI 回归脚本更新

`scripts/ci_regression.sh` 更新 import 路径：
```bash
# 改造前
export PYTHONPATH="$SKILL_DIR:$PYTHONPATH"

# 改造后
export PYTHONPATH="$WORKSPACE/infrastructure:$SKILL_DIR:$PYTHONPATH"
```

---

## 5. Skill 主入口改造

### 5.1 `__init__.py` 精简

**当前**：4153 行，包含大量自学习初始化代码

**改造要点**：
```python
# 改造前（__init__.py 中直接初始化自学习）：
from learn.collector import init_feedback_collector
# ... 200+ 行初始化代码 ...

# 改造后（通过 integration 层间接使用）：
try:
    from integrations.order_self_learning import init_order_learning
    init_order_learning(self.db_config)
except ImportError:
    logger.warning("自学习模块未安装，跳过学习功能")
```

**效果**：
- Skill 主入口不硬依赖自学习模块
- 自学习模块可以独立安装/卸载
- 没有自学习模块时，Skill 仍能正常处理订单

### 5.2 EventBus emit 保留

Skill 中的 `EventBus.emit(...)` 调用**保留不变** — 这是事件源，不是消费者。

```python
# Skill 继续 emit 事件（不变）
EventBus.emit("store_confirm_needed", {...})
EventBus.emit("sku_confirmed", {...})

# 自学习模块在 integration 层订阅（已拆出）
EventBus.on("store_confirm_needed", order_collector_hooks.on_store_confirm_needed)
```

---

## 6. 数据库表拆分

### 6.1 当前数据库表

| 表名 | 所属模块 | 拆分后归属 |
|------|---------|-----------|
| `product_sku` | 订单 Skill | Skill（不动） |
| `product_name_alias` | 订单 Skill | Skill（不动） |
| `store_list` | 订单 Skill | Skill（不动） |
| `warehouse_code_mapping` | 订单 Skill | Skill（不动） |
| `customer` | 订单 Skill | Skill（不动） |
| `order_feedback` | 自学习 | self_learning |
| `order_corrections` | 自学习 | self_learning |
| `layer_success_rate` | 自学习 | self_learning |

### 6.2 数据库拆分策略

**短期（本次）**：不改数据库，表名不变，只改代码层的归属。

**长期（可选）**：如果需要独立部署，可以把自学习相关的 3 张表迁移到独立的数据库/Schema。

---

## 7. 实施时间线

| Phase | 内容 | 预计耗时 | 风险 | 可独立执行 |
|-------|------|---------|------|-----------|
| **Phase 1** | 提取 EventBus | 15 分钟 | 低 | ✅ |
| **Phase 2a** | 提取自学习核心框架 | 45 分钟 | 中 | 依赖 Phase 1 |
| **Phase 2b** | 迁移分析脚本 | 20 分钟 | 低 | 依赖 Phase 2a |
| **Phase 2c** | 创建订单适配层 | 30 分钟 | 低 | 依赖 Phase 2a |
| **Phase 3** | 提取记忆模块 | 30 分钟 | 低 | 独立 |
| **Phase 4** | 整理运维脚本 | 20 分钟 | 低 | 独立 |
| **Phase 5** | 更新 launchd + CI | 20 分钟 | 中 | 依赖 Phase 2-4 |
| **Phase 6** | 全面回归测试 | 30 分钟 | - | 依赖全部 |

**总预计**：3-4 小时

### 推荐执行顺序

```
Phase 1 (EventBus)
    ↓
Phase 2a (自学习核心) → Phase 2b (分析脚本) → Phase 2c (适配层)
                                                        ↓
Phase 3 (记忆) ──────────────────────────────→ Phase 5 (launchd/CI)
                                                        ↓
Phase 4 (运维脚本) ───────────────────→ Phase 6 (回归测试)
```

---

## 8. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| import 路径断裂 | 高 | 中 | 每个 Phase 完成后跑 CI 回归 |
| launchd 定时任务失效 | 中 | 低 | Phase 5 统一更新 + `install_launchd.sh` 重新安装 |
| 自学习数据丢失 | 低 | 高 | 不改数据库，只改代码层 |
| Skill 主入口改动引入 bug | 中 | 高 | 用 shim 保持向后兼容，逐步切换 |
| 记忆协议路径变更影响 AI 行为 | 中 | 中 | AGENTS.md / MEMORY.md 同步更新路径 |

---

## 9. 复用场景

拆分完成后，新项目可以直接复用：

| 项目 | 复用模块 | 接入方式 |
|------|---------|---------|
| AI 客服 | `self_learning/` + `memory_system/` + `event_bus/` | 定义客服事件 map |
| 供应链计划 | `self_learning/` + `memory_system/` | 定义供应链事件 map |
| 新项目 | 任意组合 | `from infrastructure.xxx import ...` |

---

## 10. 验收标准

- [ ] `scripts/ci_regression.sh` 全量通过（53/53）
- [ ] `bash ops/daily_wrap.sh --no-feishu` 正常执行
- [ ] launchd 3 个 plist 全部 reload 成功
- [ ] Skill `execute()` 端到端跑通（1 单 1 多门店）
- [ ] 自学习 `analyze_data.py` 正常生成报告
- [ ] `memory/` 日志读写正常
- [ ] `grep -r "jinqianfei" infrastructure/` = 0（无硬编码路径）
- [ ] `infrastructure/` 可以直接 `cp` 到另一个项目使用

---

## 11. 不在本次范围

- ❌ 不改数据库结构
- ❌ 不拆分 Skill 内部的 tools/（已经够清晰）
- ❌ 不把 `infrastructure/` 做成独立的 Python 包（pip install）— 等复用需求出现时再做
- ❌ 不迁移到阿里云 — 拆分完成后再考虑

---

*文档结束 — 等待金姐确认后开始执行*
