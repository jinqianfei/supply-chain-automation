# skill_ops_monitor - 运营监控平台

**版本**: v1.0 (Phase 1)  
**日期**: 2026-05-29  
**状态**: 规划中，待开发  

---

## 概述

多 Agent 运营监控平台，监控 OpenClaw 上多个 AI Agent 的：
- 思维链（Reasoning Steps）
- 工具链（Tool Calls）
- 用户反馈（User Feedback）
- 处理结果（Order Metrics）
- 异常告警（Alert Events）

**首个试点**: AI建单助手（skill_order_to_huading_template v5.3）  
**扩展目标**: 支持 N 个 Agent 接入

---

## 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│              Ops Monitor (运营监控平台)                       │
│              独立飞书机器人 / 独立 Agent                       │
├─────────────────────────────────────────────────────────────┤
│  监控目标                                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ AI建单助手   │  │ Agent B     │  │ Agent C      │  ...   │
│  │ (当前试点)   │  │ (后续接入)  │  │ (后续接入)  │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
├─────────────────────────────────────────────────────────────┤
│  数据采集                                                    │
│  sessions_history() │ memory_search() │ 飞书消息           │
├─────────────────────────────────────────────────────────────┤
│  数据存储（neo 数据库）                                       │
│  order_metrics │ session_traces │ user_feedback            │
│  monitored_agents │ alert_events                          │
├─────────────────────────────────────────────────────────────┤
│  报表 & 告警                                                 │
│  日报推送 │ 异常告警 │ 趋势分析 │ Agent 对比                │
└─────────────────────────────────────────────────────────────┘
```

---

## 数据库设计

### 表 1: order_metrics（订单指标）

```sql
CREATE TABLE order_metrics (
    id SERIAL PRIMARY KEY,
    agent_id TEXT NOT NULL,           -- agent 标识：ai-order / ai-agent-b / ...
    session_id TEXT,                  -- OpenClaw session ID
    order_date DATE,
    order_type TEXT,                  -- excel / image / pdf / word / text
    store_count INT,                   -- 门店数量
    sku_count INT,                    -- SKU 总数量
    matched_sku_count INT,           -- 匹配成功数量
    unmatched_sku_count INT,          -- 未匹配数量
    match_rate FLOAT,                 -- 匹配率 (matched_sku_count / sku_count)
    owner_code TEXT,                  -- 货主ID
    output_file TEXT,                 -- 生成文件路径
    processing_time_ms INT,           -- 总处理时长（毫秒）
    status TEXT,                      -- success / failed / user_rejected / in_progress
    error_message TEXT,               -- 错误信息（如有）
    skill_version TEXT,               -- 使用的 skill 版本
    created_at TIMESTAMP DEFAULT NOW()
);

-- 索引
CREATE INDEX idx_order_metrics_agent_id ON order_metrics(agent_id);
CREATE INDEX idx_order_metrics_order_date ON order_metrics(order_date);
CREATE INDEX idx_order_metrics_status ON order_metrics(status);
```

### 表 2: session_traces（会话链路）

```sql
CREATE TABLE session_traces (
    id SERIAL PRIMARY KEY,
    agent_id TEXT NOT NULL,           -- agent 标识
    session_id TEXT,                  -- OpenClaw session ID
    order_id INT REFERENCES order_metrics(id),
    step_name TEXT,                   -- 步骤名：tools_parse / _match_store / _match_sku 等
    step_type TEXT,                   -- reasoning(思维链) / tool_call(工具调用) / user_action(用户交互) / system(系统)
    content TEXT,                     -- 内容（文本，truncate 到 4000）
    tool_name TEXT,                   -- 工具名（如 step_type=tool_call）
    tool_args JSONB,                  -- 工具参数（如有）
    tool_result TEXT,                 -- 工具返回（文本摘要）
    confidence FLOAT,                -- 置信度（SKU 匹配时）
    duration_ms INT,                  -- 本步耗时（毫秒）
    created_at TIMESTAMP DEFAULT NOW()
);

-- 索引
CREATE INDEX idx_traces_agent_id ON session_traces(agent_id);
CREATE INDEX idx_traces_session_id ON session_traces(session_id);
CREATE INDEX idx_traces_step_type ON session_traces(step_type);
```

### 表 3: user_feedback（用户反馈）

```sql
CREATE TABLE user_feedback (
    id SERIAL PRIMARY KEY,
    agent_id TEXT NOT NULL,           -- agent 标识
    session_id TEXT,
    order_id INT REFERENCES order_metrics(id),
    feedback_type TEXT,              -- store_confirm(门店确认) / sku_confirm(SKU确认) / modify(修改) / reject(拒绝) / accept(接受)
    original_value TEXT,              -- 原始值
    user_value TEXT,                  -- 用户修改/确认值
    comment TEXT,                     -- 用户备注
    confidence FLOAT,                -- 涉及置信度时记录
    created_at TIMESTAMP DEFAULT NOW()
);

-- 索引
CREATE INDEX idx_feedback_agent_id ON user_feedback(agent_id);
CREATE INDEX idx_feedback_type ON user_feedback(feedback_type);
```

### 表 4: monitored_agents（被监控 Agent 注册表）

```sql
CREATE TABLE monitored_agents (
    id SERIAL PRIMARY KEY,
    agent_id TEXT UNIQUE NOT NULL,    -- OpenClaw agent ID（唯一标识）
    agent_name TEXT,                  -- 显示名称
    description TEXT,                -- Agent 描述
    owner_channel TEXT,              -- 主所有者飞书 open_id
    webhook_url TEXT,                -- 告警 webhook（如有）
    notification_schedule TEXT,      -- 推送日程：daily_17:00 / hourly / on_demand
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 初始数据：AI建单助手
INSERT INTO monitored_agents (agent_id, agent_name, description, notification_schedule) VALUES
('ai-order', 'AI建单助手', '订单转换机器人，基于 skill_order_to_huading_template v5.3', 'daily_17:00');
```

### 表 5: alert_events（告警事件）

```sql
CREATE TABLE alert_events (
    id SERIAL PRIMARY KEY,
    agent_id TEXT NOT NULL,           -- agent 标识
    order_id INT REFERENCES order_metrics(id),
    alert_type TEXT,                 -- low_match_rate(低匹配率) / timeout(处理超时) / user_reject(用户拒绝) / error(错误)
    severity TEXT,                   -- low / medium / high / critical
    message TEXT,                    -- 告警消息
    raw_data JSONB,                  -- 原始数据
    is_resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 索引
CREATE INDEX idx_alerts_agent_id ON alert_events(agent_id);
CREATE INDEX idx_alerts_unresolved ON alert_events(is_resolved) WHERE is_resolved = FALSE;
```

---

## 监控维度

### 通用维度（所有 Agent 适用）

| 维度 | 内容 | 采集方式 |
|------|------|---------|
| 思维链 | reasoning steps 推理过程 | sessions_history |
| 工具链 | tool_name / args / result / duration | sessions_history + includeTools |
| 用户交互 | confirm / reject / modify / accept | sessions_history user messages |
| 处理时长 | 各步耗时 + 总耗时 | timestamp 计算 |
| 会话信息 | session_id / created_at / messages_count | sessions_list |

### Agent 相关维度（AI建单助手）

| 维度 | 内容 | 采集方式 |
|------|------|---------|
| 订单类型 | excel / image / pdf / word | order parsed |
| 门店匹配 | 匹配结果 + 确认状态 | _match_store 结果 |
| SKU映射 | 匹配率 + 未匹配列表 | _match_sku 结果 |
| Skill版本 | v5.3 | 固定配置 |
| 生成文件 | output_file | template_generator 结果 |

---

## 异常判断规则

| 异常类型 | 判断条件 | 严重级别 |
|---------|---------|---------|
| SKU 低匹配率 | match_rate < 70% | medium |
| SKU 中匹配率 | 70% <= match_rate < 80% | low |
| 处理超时 | processing_time > 300000ms (5分钟) | high |
| 用户连续拒绝 | 2次+ reject 在同一 session | high |
| 工具调用失败 | tool_result contains "error" | high |
| 未匹配SKU存在 | unmatched_count > 0 | low |
| 会话中断 | status = in_progress 但超过30分钟无更新 | medium |

---

## 报表设计

### 日报格式

```
📊 OpenClaw 运营日报 | {date}

═══════════════════════════════════
🤖 AI建单助手（skill v5.3）
═══════════════════════════════════
📈 今日概览
├── 新增订单：12 单
├── 成功处理：11 单（91.7%）
├── 失败处理：0 单
├── 用户拒绝：1 单
└── 平均处理时长：45s

📦 门店 & SKU 统计
├── 门店匹配确认率：100%（含用户修改）
├── SKU 总匹配率：94.2%
├── 未匹配SKU：3 个（订单 #5）
└── 最低匹配率：订单 #5（62%）

🛠️ 工具使用统计
├── tools_parse：12次
├── _match_store：12次
├── _match_sku：12次
├── template_generator：11次
└── 总工具调用：47次

⚠️ 异常告警
├── 🔴 订单 #5：SKU匹配率仅 62%（<70%阈值）
└── 🟡 订单 #8：处理时长 6分23秒（>5分钟阈值）

💬 用户反馈
├── 门店确认修改：1次（制茶青年→制茶青年(旗舰店)）
├── SKU确认修改：0次
└── 拒绝处理：1次

═══════════════════════════════════
🤖 [Agent B 名称]（待接入）
═══════════════════════════════════
暂无数据
```

### 周报格式（扩展）

- 趋势图：订单量、处理成功率、平均时长
- 对比图：各 Agent 数据对比
- Top 异常：高频异常类型统计
- 用户反馈汇总：修改类型分布

---

## Skill 文件结构

```
skills/skill_ops_monitor/
├── SKILL.md                      # 本文档
├── __init__.py                   # 主入口，execute()
├── config.py                     # 数据库配置、Agent 注册
├── tools/
│   ├── session_collector.py     # sessions_list + sessions_history 采集
│   ├── trace_parser.py           # 解析 reasoning + tool_calls + user messages
│   ├── metrics_calculator.py     # 计算 match_rate / processing_time 等
│   ├── alert_detector.py         # 异常检测
│   ├── report_generator.py       # 生成日报/周报
│   └── feishu_publisher.py       # 飞书推送
├── templates/
│   ├── daily_report.md           # 日报模板
│   └── weekly_report.md          # 周报模板
└── sql/
    └── init_tables.sql           # 建表语句
```

---

## 实施计划

| Phase | 任务 | 产出 | 状态 |
|-------|------|------|------|
| **Phase 1** | 创建数据库表 | SQL 建表脚本 | 待开发 |
| **Phase 1** | 开发 session_collector | 数据采集工具 | 待开发 |
| **Phase 1** | 开发 trace_parser | 解析思维链/工具链 | 待开发 |
| **Phase 1** | 开发 metrics_calculator | 指标计算 | 待开发 |
| **Phase 1** | 接入 AI建单助手 | 完整监控试点 | 待开发 |
| **Phase 2** | 开发 alert_detector | 异常检测 | 待开发 |
| **Phase 2** | 开发 report_generator | 报表生成 | 待开发 |
| **Phase 2** | 抽象通用采集层 | 支持多 Agent | 待开发 |
| **Phase 3** | 飞书推送配置 | 定时日报 | 待开发 |
| **Phase 4** | 告警实时推送 | 即时通知 | 待开发 |
| **Phase 5** | 管理后台 | 接入新 Agent 配置 | 待规划 |

---

## 技术要点

### 1. sessions_history 采集

```python
# 采集最近活跃 session
sessions = sessions_list(
    agentId="ai-order",
    activeMinutes=60
)

# 拉取完整链路
history = sessions_history(
    sessionKey=session.key,
    includeTools=True
)
```

### 2. 思维链解析

- Assistant 消息中的 `**思` 或 `**思考` 段落
- 正则提取：`r'\*\*(思|思考)[^*]*\*\*(.*?)(?=\*\*|$)'`

### 3. 工具调用解析

- `tool_calls` 数组中：`name` / `arguments` / `result`
- 计算每步 duration：相邻 tool_call 的 timestamp 差

### 4. 用户反馈解析

- user 消息中包含 `confirm` / `reject` / `modify` 关键词
- 提取 `need_store_confirm=True` / `need_sku_confirm=True` 状态

---

## 依赖

- OpenClaw sessions 工具：`sessions_list`, `sessions_history`
- 数据库：neo (localhost:5432/neo)
- 消息推送：飞书 message tool

---

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-05-29 | 初始规划 |

---

*由 AI建单助手 创建*