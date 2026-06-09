# AGENTS.md - 工作区规则

> **更新记录**: V2.0 (2026-04-20) — 适配 OpenClaw 平台架构，去除自建服务引用，更新 Phase 1-3 能力规则

## Session Startup 规则

每次会话启动时，必须按以下顺序执行：

1. **读取 IDENTITY.md** - 加载Agent身份定义、团队成员和工作流程
2. **读取 SOUL.md** - 加载核心个性特质
3. **读取 USER.md** - 加载用户信息
4. **读取 TOOLS.md** - 加载全部 40 个工具函数配置
5. **读取 prompts/ 目录** - 加载所有Worker Agent的System Prompt：
   - `prompts/orchestrator.md` - 决策协调Agent完整Prompt
   - `prompts/demand_forecast.md` - 需求预测Agent
   - `prompts/production_planning.md` - 生产计划Agent
   - `prompts/inventory_optimization.md` - 库存优化Agent
   - `prompts/procurement.md` - 采购计划Agent
   - `prompts/exception_handling.md` - 异常处理Agent

## Memory 规则

- 使用 `read_blackboard` / `write_blackboard` 在Agent间共享数据
- 黑板数据是Agent间通信的唯一通道
- 每次写入黑板时需标注 `agent_id` 和 `tags`，便于追溯
- 关键决策和推理过程必须记录到黑板，确保可追溯性
- 多轮对话上下文通过 `manage_context` 工具管理，支持指代消解和累积上下文

## Red Lines（红线规则）

以下规则不可违反：

1. **数据优先** - 所有决策必须基于数据，禁止主观臆断
2. **不猜测** - 信息不足时主动追问用户，不得自行假设
3. **保守原则** - 不确定时选择风险更低的方案，提供多个备选而非单一推荐
4. **人工确认** - 涉及VIP客户、大额采购、产能冲突等关键决策必须标记 `[需人工确认]`
5. **不超越职责** - Orchestrator不直接调用数据读取类工具，通过 `dispatch_task` 分发给Worker Agent
6. **不跳过异常** - L1致命异常必须立即上报，不得延迟或忽略
7. **工具调用强制** - 生成报告前必须调用对应数据工具获取真实数据，禁止用估算/缓存数据代替（详见 "报告数据检查规则"）

## 进度汇报规则（长链路任务）

### 触发条件
当任务满足以下任一条件时，必须启动定时汇报机制：
- 任务涉及多个子步骤，执行时间预计超过 5 分钟
- 任务通过 `sessions_spawn` 启动子 Agent 并行执行
- 任务涉及远程服务器配置（EC2 部署、环境搭建等）
- 任务涉及数据同步、文件传输等 I/O 操作

### 汇报时机

| 阶段 | 触发时机 |
|------|----------|
| **开始** | 任务刚启动，确认已开始执行 |
| **中继** | 每个子步骤完成时 |
| **阶段完成** | 里程碑达成时（如 EC2 创建完成、MCP 部署完成） |
| **异常** | 遇到错误、失败、重试时 |
| **完成** | 任务全部完成或有明确最终结果时 |

### 汇报内容

```
📊 任务进度汇报

- 当前阶段：[具体名称]
- 已完成：[子任务列表]
- 进行中：[当前任务]
- 遇到问题：[如有]
- 下一步：[接下来的步骤]
- 预计完成：[时间估算]
```

### 格式要求
- 使用表格呈现多项目状态
- 使用 emoji 区分状态：✅完成 ⏳进行中 ❌失败 ⏸️等待
- 问题描述要具体，说明原因和解决方案
- 主动询问用户是否继续或调整方向

---

## 开发任务规则

### 任务分发

- 通过 `dispatch_task` 分发子任务，明确指定 `agent_id`、`task_type`、`task_params`、`priority`
- 无依赖的子任务必须并行执行（如 production_agent 和 inventory_agent）
- 有依赖的子任务按依赖关系串行执行

### 结果整合

- 收集所有Worker Agent结果后执行一致性检查
- 需求预测总量 vs 生产计划总量偏差 > 5% 需标注
- 产能、物料、交期约束不满足时触发冲突解决流程

### 错误处理

- 子任务失败时按策略处理：retry(3次) -> skip(默认值) -> fallback(LLM推理) -> abort(终止)
- 每个步骤默认超时60秒，决策协调超时120秒

### 输出要求

- 最终方案通过 `generate_report` 生成结构化报告
- 关键数据用表格呈现，行动建议用编号列表
- `[需人工确认]` 标记必须醒目

---

## Phase 1-3 差异化能力规则

### Phase 1: 交互革命

#### 意图理解规则
- 用户输入必须先经过 `parse_intent` 处理，不得直接路由
- 置信度 ≥ 0.85：直接执行对应工作流或Agent调用
- 置信度 0.60-0.85：生成追问问题，等待用户补充
- 置信度 < 0.60：降级为自由对话（INT-12），通过知识库问答

#### 上下文管理规则
- 每个用户会话通过 `manage_context` 创建独立上下文
- 跨轮次对话中的指代（"那个产品"、"上个月"）必须通过 `resolve_references` 消解
- 会话 TTL 默认 120 分钟，过期自动清理

#### 报告生成规则
- 所有最终输出必须通过 `generate_report` 生成，不得自由格式输出
- 月度计划/S&OP 使用 full 模式，查询结果默认 brief 模式
- 用户可指定 "给我看详细版" 或 "简单说" 切换模式

#### 报告数据检查规则（硬性要求）

**每次生成报告前，必须确认数据freshness**：

| 条件 | 要求 |
|------|------|
| 数据获取时间 > 5分钟 | **必须重新调用工具**获取最新数据 |
| 数据获取时间 ≤ 5分钟 | 可复用，但需标注数据时间 |
| 数据从未获取 | **必须调用工具**，禁止估算 |

**数据类工具清单**：
- `read_sales_data` - 销售数据
- `read_inventory` - 库存数据
- `read_capacity` - 产能数据
- `read_suppliers` - 供应商数据
- `read_bom` - BOM数据
- `generate_forecast` - 预测数据
- `optimize_schedule` - 排产数据
- `scan_all_plans` - 计划扫描数据
- `read_sales_data` - 销售数据

**不满足条件的报告必须标注**：
```
⚠️ **数据说明**：本报告使用了[工具名]于[时间]获取的数据，
数据距今已超过5分钟，[已重新获取/未重新获取]
```

**示例**：
- ✅ 正确：生成报告前调用 `read_inventory`，获取时间 17:47，报告内数据新鲜
- ❌ 错误：复用17:00获取的数据生成17:30的报告，未重新调用工具


### Phase 2: 数据边界突破

#### 外部数据接入规则
- `fetch_external_data` 统一入口拉取外部数据，禁止直接调用 API
- 数据拉取结果写入黑板，供对应 Agent 消费
- 天气数据每天 06:00 拉取，新闻每 4 小时，金融数据每天 09:00

#### 信号处理规则
- 非结构化文本通过 `extract_signals` 提取信号，支持 9 种信号类型
- 多源信号通过 `fuse_signals` 融合，输出综合影响评估
- 融合结果写入黑板 `fused_signals` 键，供所有 Agent 消费

#### 知识库检索规则
- 所有 Agent 均可通过 `search_knowledge_base` 检索知识库
- 检索结果仅供参考，不得替代数据分析

### Phase 3: 智能体闭环

#### 执行引擎规则
- 方案执行必须通过 `submit_action_plan` 提交，自动判断风险级别
- LOW/MEDIUM 级别自动执行并通知，HIGH/CRITICAL 级别必须人工审批
- 执行后通过 `track_execution` 跟踪效果，计算偏差

#### 反馈学习规则
- 预测结果与实际数据对比后，通过 `collect_feedback` 收集偏差
- 偏差分析通过 `analyze_deviations` 执行，输出根因和改进建议
- 参数调优通过 `auto_tune_model` 执行，调优幅度受限（防止震荡）
- 关键决策和执行结果通过经验库记录，供相似场景检索

#### 主动感知规则
- 定时巡检任务由系统调度器管理（`schedulers/monitor.ts`）
- 事件驱动触发器监听外部信号变化（`schedulers/event_triggers.ts`）
- 巡检发现异常自动推送通知，不等待用户请求

---

## 架构说明

本系统基于 **OpenClaw 开源 AI Agent 框架** 运行：
- Agent 调度、LLM 调用、消息通道由 OpenClaw 平台提供
- 工具函数通过 TOOLS.md 注册，由 OpenClaw 平台调用
- Agent 行为通过 prompts/*.md 配置，由 OpenClaw 平台加载
- 飞书通道通过 OpenClaw 平台内置能力集成

详见 [架构回归方案](../OpenClaw架构回归方案.md)

---

## 📋 记忆系统

**按需读取：**
- 提到某项目 → 读 `memory/projects/<项目>/PROJECT.md` + `sessions/INDEX.md`
- 提到凭证/密码 → 读 `memory/credentials/INDEX.md`
- 提到"继续上次" → 读对应项目的最新 sessions/ 记录
- 提到"之前说过" → 读 `MEMORY.md`

**每次结束会话时必须执行：**
1. 执行 `memory/SESSION_END_PROTOCOL.md`
2. 更新 `MEMORY.md`「最近会话摘要」
3. 更新 `projects/<项目>/sessions/` + `skills/INDEX.md`

**参考：** `memory/SESSION_START_PROTOCOL.md`、`memory/SESSION_END_PROTOCOL.md`、`memory/projects/PROJECT_TEMPLATE.md`

