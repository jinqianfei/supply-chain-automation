# AI建单助手 — 自学习模块完整方案 v1.0

> **作者**：AI建单助手
> **日期**：2026-06-11
> **状态**：方案已确认，开始实施
> **配套文档**：`MEMORY_SYSTEM_PLAN.md`（记忆模块）、`METHODOLOGY_SKILL_ITERATION.md`（方法论）

---

## 0. 方案概述

### 目标

让 Skill 从每次订单处理中**自动学习**，通过数据分析发现问题模式，自动或半自动地改进匹配逻辑，形成"处理→采集→分析→改进→验证"的闭环飞轮。

### 核心原则

1. **数据驱动**：所有改进建议必须有数据支撑，不凭感觉改
2. **人工确认**：系统级改动必须金姐确认后执行
3. **不改原代码**：改进走新分支 + CI 验证流程
4. **配置化通知**：推送对象、推送渠道、推送频率都可配置
5. **yaml 优先**：别名/映射规则用 yaml 文件存储，不用 DB 表

---

## 1. 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                        自学习模块架构                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐   │
│  │ L1 采集层 │ →  │ L2 分析层 │ →  │ L3 改进层 │ →  │ L4 验证层 │   │
│  │(EventBus)│    │(分析脚本) │    │(yaml/代码)│    │(CI+回放)  │   │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘   │
│       ↓               ↓               ↓               ↓         │
│  10个事件        高频纠正发现     别名表扩充       CI回归53测试    │
│  → 3张DB表       层成功率统计     阈值调优         历史订单回放    │
│  (order_feedback  阈值调优建议     关键词词库       准确率对比     │
│   order_corrections                清洗规则                       │
│   layer_success_rate)              新增匹配层                    │
│                                                                   │
├─────────────────────────────────────────────────────────────────┤
│                      通知机制（配置化）                            │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ notification_config.yaml                                  │   │
│  │  • 推送对象：金姐（可按改进类型分配不同审批人）              │   │
│  │  • 推送渠道：飞书 / 钉钉（可切换）                         │   │
│  │  • 推送频率：别名表每天10点汇总，其他发现即推              │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. L1 采集层（✅ 已完成）

### 2.1 事件总线

**文件**：`events/bus.py`（40行，纯标准库）

```python
EventBus.on("store_confirm_needed", handler)
EventBus.emit("store_confirm_needed", {data...})
```

**10 个事件**（8/10 已 emit，2 个暂无触发场景）：

| 事件 | 状态 | 触发时机 |
|------|------|---------|
| store_confirm_needed | ✅ | 门店匹配后需确认 |
| store_confirmed | ✅ | 用户确认门店 |
| store_corrected | ✅ | 用户纠正门店 |
| sku_confirm_needed | ✅ | SKU匹配后需确认 |
| sku_confirmed | ✅ | 用户确认SKU |
| sku_corrected | ✅ | 用户纠正SKU |
| order_complete | ✅ | 订单处理完成 |
| user_modified | ✅ | 用户修改字段 |
| order_cancelled | ❌ | 暂无取消流程 |
| alert_raised | ❌ | 暂无告警触发点 |

### 2.2 数据库表（3张）

| 表 | 字段数 | 用途 |
|---|--------|------|
| order_feedback | 22 | 每次订单处理的完整反馈（匹配率/时长/版本等） |
| order_corrections | 8 | 每条纠正记录（门店/SKU/单位/数量/规格） |
| layer_success_rate | 11 | 各匹配层成功率统计（总尝试/成功/纠正/平均分） |

### 2.3 订单提交人追踪（待新增）

为支持多用户场景，order_feedback 表需新增 `submitted_by` 字段：

```sql
ALTER TABLE order_feedback ADD COLUMN submitted_by VARCHAR;
```

- 飞书：从消息的 sender_id 提取
- 钉钉：从消息的 senderStaffId 提取
- 通知时根据 submitted_by 路由到对应审批人

---

## 3. L2 分析层（✅ 已完成）

### 3.1 分析脚本

**文件**：`scripts/analyze_learning_data.py`

**数据来源**：3 张 DB 表（每次订单处理自动写入）

| 分析项 | 时间范围 | 触发条件 | 输出 |
|--------|---------|---------|------|
| 高频纠正商品 → 别名表候选 | 滚动 7 天 | 同一(商品名,正确名) ≥ 3 次 | INSERT yaml |
| 未知字段名 → 字段别名候选 | 滚动 7 天 | 同一(字段名,货主) ≥ 2 次 | INSERT yaml |
| 各层成功率 | 累计全量 | 每层 ≥ 50 次尝试 | 发现薄弱层 |
| 阈值调优建议 | 滚动 30 天 | 某层纠正率 > 30% | 建议调阈值 |
| 关键词词库更新 | 滚动 30 天 | 新产品类型词反复出现 | 建议加词 |
| 清洗规则增强 | 滚动 30 天 | 新边界字符反复出现 | 建议改正则 |

### 3.2 每日别名表汇总

**文件**：`scripts/daily_alias_summary.py`

**触发**：每天 10:00（cron）

**逻辑**：
1. 查昨天的 order_corrections（correction_type='sku'）
2. 统计 (entity_name, corrected_value) 出现次数
3. ≥ 2 次的生成建议
4. 推送到飞书/钉钉（和日报分开，独立推送）

**输出示例**：
```
📋 别名表改进建议（昨日汇总）

  • "果糖-" → "果糖/新" (5次)
  • "潮迹牛肉丸" → "潮迹潮汕牛肉丸" (3次)

→ 回复"确认"执行 / "跳过"忽略
```

---

## 4. L3 改进层（✅ 核心已完成）

### 4.1 改进类型 × 风险等级 × 审批流程

| 改进类型 | 风险 | 改动范围 | 审批流程 |
|----------|------|---------|---------|
| 别名表扩充 | 🟢低 | yaml 文件 INSERT | 每天10点汇总推送，金姐确认 |
| 字段名别名扩充 | 🟢低 | yaml 文件 INSERT | 每天10点汇总推送，金姐确认 |
| 阈值调优 | 🟡中 | _sku_mapper.py 常量 | 发现即推→新分支→CI→金姐确认 |
| 关键词词库更新 | 🟡中 | _sku_mapper.py 列表 | 发现即推→新分支→CI→金姐确认 |
| 清洗规则增强 | 🔴高 | _sku_mapper.py 正则 | 发现即推→新分支→CI→金姐确认 |
| 新增匹配层 | 🔴高 | _sku_mapper.py 新增Layer | 发现即推→新分支→CI→金姐确认 |

### 4.2 别名表扩充逻辑

**存储**：yaml 文件（和现有 field_mapping/rules/ 一致）

```yaml
# field_mapping/rules/sku_aliases_auto.yaml
aliases:
  - order_product_name: "果糖-"
    system_product_name: "果糖/新"
    shipper_id: "HZ2023061500002"
    source: "auto"  # auto / manual
    correction_count: 5
    confirmed_at: "2026-06-11"
```

**加载优先级**：yaml 别名 > DB product_name_alias > 现有 Layer 0-3

**多 SKU 问题**：别名匹配到商品名后，如果有多个 SKU（如"果糖/新"对应桶和箱），结合 order_unit 选 SKU（复用 v5.14.0 的 _resolve_unit_type 逻辑）。

### 4.3 字段名别名扩充

**存储**：yaml 文件

```yaml
# field_mapping/rules/field_aliases_auto.yaml
aliases:
  - raw_field_name: "配送点名称"
    standard_field: "store_name"
    shipper_id: "HZ2023061500002"  # 可为空=通用
    source: "auto"
    confirm_count: 3
```

**加载优先级**：yaml 字段别名 > FIELD_ALIAS_MAPPING 硬编码

### 4.4 阈值调优

**当前阈值**（_sku_mapper.py）：

| 阈值 | 当前值 | 调优依据 |
|------|--------|---------|
| Layer 2 直接返回 | ≥ 0.8 | 纠正率 > 30% → 降低 |
| Layer 2 需确认 | ≥ 0.7 | 纠正率 > 30% → 降低 |
| Layer 3 返回 | ≥ 0.7 | 纠正率 > 30% → 降低 |
| keyword_boost 强 | 0.25 | 有boost也被纠正 → 降低 |
| keyword_boost 弱 | 0.10 | 有boost也被纠正 → 降低 |
| unit加成 | +0.20 | unit匹配仍被纠正 → 降低 |
| spec加成 | +0.10 | spec匹配仍被纠正 → 降低 |

**调优流程**：分析脚本输出建议值 → 跑历史订单回放 → 对比准确率 → 金姐确认 → 改代码

### 4.5 关键词词库更新

**当前词库**（_sku_mapper.py）：
- product_types: ['鸡排', '片', '肠', '翅', '腿', '排', ...]
- flavor_types: ['酱料', '粉', '膏']

**更新触发**：order_corrections 中发现新产品类型词反复出现

### 4.6 清洗规则增强 / 新增匹配层

**流程**：
1. 分析脚本发现模式
2. AI 在新分支上写代码（不动 main）
3. 跑 CI 回归（53 测试）
4. 跑历史订单回放
5. 生成报告（改了什么 + 为什么 + CI 结果 + 准确率对比）
6. 推送给金姐确认
7. 金姐确认 → merge 到 main

---

## 5. L4 验证层（✅ 已完成）

### 5.1 CI 回归测试

```bash
bash scripts/ci_regression.sh
# 8 步骤，53 个 SKU 测试 + 21 个映射测试 + 4 个事件管道测试
```

### 5.2 历史订单回放

```python
# tests/history_replay.py
# 从 order_feedback 表取出历史订单的 source_file
# 用新版 Skill 重跑，对比匹配结果
```

### 5.3 准确率对比

```
旧版准确率: 85%
新版准确率: 88%
提升: +3%
→ 建议上线
```

---

## 6. 通知机制

### 6.1 配置文件

**文件**：`config/notification_config.yaml`

> 2026-06-12 更新：user_id 改为环境变量引用 `${FEISHU_ADMIN_ID:-默认值}`，无硬编码。

```yaml
users:
  - user_id: "${FEISHU_ADMIN_ID:-ou_3ca0a1a1f283c774915d4656143464cc}"
    name: "金倩菲"
    channel: "feishu"
    role: "admin"

approvers:
  alias_expansion:  [{ role: "admin" }]
  threshold_tuning: [{ role: "admin" }]
  keyword_update:   [{ role: "admin" }]
  cleaning_rule:    [{ role: "admin" }]
  new_layer:        [{ role: "admin" }]

schedule:
  alias_expansion: "daily_10am"
  threshold_tuning: "on_discovery"
  keyword_update: "on_discovery"
  cleaning_rule: "on_discovery"
  new_layer: "on_discovery"
```

### 6.2 推送频率

| 改进类型 | 频率 | 原因 |
|----------|------|------|
| 别名表扩充 | 每天 10:00 汇总 | 低频改进，批量推送减少打扰 |
| 字段名别名 | 每天 10:00 汇总 | 同上 |
| 阈值调优 | 发现即推 | 中频，需要及时确认 |
| 关键词词库 | 发现即推 | 中频 |
| 清洗规则 | 发现即推 | 低频，高风险 |
| 新增匹配层 | 发现即推 | 极低频，高风险 |

### 6.3 IM 切换

切换飞书→钉钉只需改 notification_config.yaml 中的 channel 字段，无需改代码。

---

## 7. 多用户场景

### 7.1 问题

云服务器上多个用户和钉钉机器人交互，AI 怎么知道通知发给谁？

### 7.2 方案

1. **订单提交时记录 submitted_by**：从 IM 消息提取 sender_id
2. **纠正时记录纠正人**：order_corrections 表新增 corrected_by 字段
3. **通知路由**：
   - 别名表扩充 → 推给对应货主的审批人
   - 阈值调优 → 推给系统管理员（金姐）
   - 关键词/清洗规则 → 推给系统管理员

### 7.3 数据库变更

```sql
ALTER TABLE order_feedback ADD COLUMN submitted_by VARCHAR;
ALTER TABLE order_corrections ADD COLUMN corrected_by VARCHAR;
```

---

## 8. 云服务器迁移适配

### 8.1 影响点

| 组件 | Mac 当前 | 云服务器 | 改动 |
|------|---------|---------|------|
| 数据库 | AWS RDS | 阿里云 RDS | .env 改 host/password |
| IM | 飞书 | 钉钉 | notification_config.yaml |
| 定时任务 | launchd | cron | 格式转换 |
| Supermemory | 云端 | 可能不通 | 本地化（已有方案） |
| Git | GitHub | 内网可能不通 | tar 打包传输 |
| 服务器访问 | SSH | 内网 | 无 SSH 隧道 |

### 8.2 记忆模块本地化

Supermemory 内网不通时的替代方案：

| Supermemory 功能 | 本地替代 |
|------------------|---------|
| 自动注入长期记忆 | AGENTS.md + MEMORY.md（已有） |
| supermemory_store | 写入 DB agent_memory 表 |
| supermemory_search | 查 DB agent_memory 表 |
| supermemory_profile | 查 DB agent_memory 表 |

**已有本地记忆**（直接迁移）：
- memory/ 目录（SESSION_START/END/PENDING 协议 + 会话日志）
- MEMORY.md（版本摘要）
- events/bus.py（事件总线）
- learn/collector.py（反馈采集器）

---

## 9. 实施路线图

### Phase 1：采集层（✅ 已完成 — v5.15.2 修复 store_corrected 误触发）
- [x] EventBus 事件总线
- [x] FeedbackCollector 反馈采集器
- [x] 3 张数据库表 + submitted_by/corrected_by 列
- [x] 10/10 事件 emit 补齐 + store_corrected 误触发修复
- [x] CI 回归测试通过

### Phase 2：分析层（✅ 已完成 — 阈值配置化，无硬编码）
- [x] 分析脚本 `scripts/analyze_learning_data.py`（阈值从 analysis_config.yaml 读取）
- [x] 每日别名表汇总 `scripts/daily_alias_summary.py`（同上）
- [x] 通知配置 `config/notification_config.yaml`（user_id 支持环境变量）
- [x] 阈值配置 `config/analysis_config.yaml`（新建）
- [x] submitted_by 字段追踪（DB 列已建 + execute 参数已加）

### Phase 3：改进层（✅ 核心已完成）
- [x] yaml 别名表文件 `field_mapping/rules/sku_aliases_auto.yaml`
- [x] yaml 字段别名文件 `field_mapping/rules/field_aliases_auto.yaml`
- [x] yaml SKU 别名加载逻辑（_sku_mapper.py _load_yaml_sku_aliases）
- [x] yaml 字段别名加载逻辑（_field_transformer.py _merge_auto_aliases）
- [x] Layer 0 多 SKU + order_unit 修复（单条+批量两处）
- [ ] 阈值调优建议逻辑（等数据积累后做）
- [ ] 关键词词库更新逻辑（等数据积累后做）

### Phase 4：验证层（✅ 已完成）
- [x] CI 回归测试
- [x] 历史订单回放脚本 `scripts/history_replay.py`（无硬编码路径）
- [x] 准确率对比报告 `scripts/accuracy_comparison.py`（无硬编码路径）

### Phase 5：通知机制（✅ 已完成）
- [x] 通知发送脚本 `scripts/notification_sender.py`（支持飞书/钉钉，无硬编码路径）
- [x] launchd 定时任务配置（3个 plist，路径改为 $AI_ORDER_WORKSPACE 单点配置）
- [ ] 多用户通知路由（迁移后完善）

---

## 10. 文件清单（2026-06-12 更新）

### 采集层（已完成）
- `events/bus.py` — EventBus 事件总线
- `learn/collector.py` — FeedbackCollector（含 v5.15.2 store_corrected 修复）
- `learn/adapter.py` — 事件 → DB 记录适配器
- `learn/schema.sql` — 建表 SQL（含 submitted_by/corrected_by）

### 分析层（已完成）
- `scripts/analyze_learning_data.py` — 分析脚本（阈值从 yaml 读取）
- `scripts/daily_alias_summary.py` — 每日别名汇总
- `config/analysis_config.yaml` — 阈值配置（新建）

### 改进层（核心已完成）
- `field_mapping/rules/sku_aliases_auto.yaml` — SKU 别名表（自动维护）
- `field_mapping/rules/field_aliases_auto.yaml` — 字段别名表（自动维护）
- `tools/_sku_mapper.py` — 已加 _load_yaml_sku_aliases
- `tools/_field_transformer.py` — 已加 _merge_auto_aliases

### 验证层（已完成）
- `scripts/history_replay.py` — 历史订单回放（无硬编码路径）
- `scripts/accuracy_comparison.py` — 准确率对比（无硬编码路径）
- `scripts/ci_regression.sh` — CI 回归测试
- `scripts/test_sku_mapper_regression.py` — SKU 回归测试
- `scripts/test_event_pipeline.py` — 事件管道测试

### 通知机制（已完成）
- `scripts/notification_sender.py` — 通知发送（支持飞书/钉钉，无硬编码）
- `config/notification_config.yaml` — 通知配置（user_id 支持环境变量）
- launchd plist × 3（路径改为 $AI_ORDER_WORKSPACE 单点配置）

### 版本文件
- `VERSION` — 5.15.2
- `CHANGELOG.md` — 含 v5.15.2 条目

---

*AI建单助手 | 2026-06-12 10:10 GMT+8*
