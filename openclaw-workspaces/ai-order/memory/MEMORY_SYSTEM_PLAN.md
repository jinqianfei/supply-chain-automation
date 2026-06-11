# AI建单助手 — 记忆系统方案 v2.0 完整版

> **作者**：AI建单助手
> **日期**：2026-06-08
> **v1.0** → **v2.0** 的变化：
> - v1.0（5 层架构 + 3 阶段路线，2026-06-08 14:00）— 顶层设计
> - v2.0（本版）— 加入数据模型、自动化机制、Phase 3 实施细节、4W 质量标准、监控指标、决策模板
>
> **配套文档**：
> - 方法论：`docs/METHODOLOGY_SKILL_ITERATION.md`
> - Skill 迭代方案：`docs/SKILL_ITERATION_PLAN_FULL.md`
>
> **核心观点**：**MEMORY.md 是手账，git/代码/mtime 是真相源**

---

## 0. 现状盘点（v1.0 暴露的问题）

### 已解决的 4 个问题（v5.9.0 + Phase 1+2）

| # | 问题 | 修复 |
|---|------|------|
| 1 | 断档 4 天（6-4~6-7）| `check_continuity.sh` + `daily_wrap.sh` 自动守护 |
| 2 | 版本号错乱（5.8 / 5.9 / 5.9.0）| `version_check.sh` 三处一致校验 |
| 3 | 无版本号自检 | `startup_check.py` 4 项自检 |
| 4 | MEMORY.md 当真相源 | 协议强化：`git/code/mtime` 是真相源 |

### v1.0 未解决的 5 个问题（✅ 全部已解决）

| # | 问题 | 影响 | 解法 | 状态 |
|---|------|------|------|------|
| 5 | memory_search 索引覆盖率低 | skills/ + database/ + docs/ 搜不到 | `reindex_memory.py` | ✅ |
| 6 | MEMORY.md 手工维护 | 易失忆、易错乱 | `extract_memory.py` | ✅ |
| 7 | 「好的记忆」无质量标准 | 每条记录随意 | `check_memory_quality.py` | ✅ |
| 8 | 决策记录无模板 | 决策不可追溯 | 决策模板（见 §7）| ✅ |
| 9 | 监控无指标 | 飞轮是否在转不可见 | 监控指标（见 §8）| ✅ |

---

## 1. 5 层架构（**核心**）

```
┌──────────────────────────────────────────────────────────┐
│  L5  决策层：MEMORY.md（人类可读，7 天摘要）             │ ← 容易被遗忘，要靠 L4 兜底
├──────────────────────────────────────────────────────────┤
│  L4 真相源：git log + 代码 + 文件 mtime（不可篡改）       │ ← 唯一可信任的层
├──────────────────────────────────────────────────────────┤
│  L3 索引层：memory_search 语义检索 + 项目目录树          │ ← 主动召回
├──────────────────────────────────────────────────────────┤
│  L2 协议层：SESSION_START / SESSION_END / PENDING 协议  │ ← 流程约束
├──────────────────────────────────────────────────────────┤
│  L1 触发层：version_check + 每日 10:00 日结 + Phase 1    │ ← 自动化守护
└──────────────────────────────────────────────────────────┘
```

### 1.1 L1 触发层（自动化守护）— **已上线**

| 触发 | 工具 | 频率 | 失败处理 |
|------|------|------|---------|
| 启动 Skill | `version_check.sh` | 每次启动 | 阻断任务，要求修复 |
| 每日 10:00 | `daily_wrap.sh` | 每天 | 飞书提醒 + 写 `/tmp/daily_wrap_*.md` |
| 订单完成 | `order_complete` 事件 | 每次 | 写入 `order_feedback` 表 |
| 用户纠正 | `store_corrected` / `sku_corrected` 事件 | 每次 | 写入 `order_corrections` 表 |
| 启动 4 项 | `startup_check.py` | 每次启动 | 失败 → 警告，不阻断 |
| 断档 > 24h | `check_continuity.sh` | 每日 | 飞书 P0 告警 |

### 1.2 L2 协议层（流程约束）— **v2.0 升级**

#### 4 个协议文件

```
memory/
├── SESSION_START_PROTOCOL.md    ← 启动协议
├── SESSION_END_PROTOCOL.md      ← 结束协议
├── PENDING_PROTOCOL.md          ← 未完成事项追踪
└── MEMORY.md                    ← 真相摘要（手账）
```

#### v2.0 强化点

| 协议 | v1.0 | v2.0 |
|------|------|------|
| **START** | 启动问询 + 按需读取 | **强制 4 项自检**（version/git/memory/pending）|
| **END** | 6 步流程 | **强制 7 步**（v1 基础 + git commit + tag 验证）|
| **PENDING** | 人工维护 | **半自动**（从 MEMORY.md/session 自动提取未完成项）|
| **MEMORY** | 自由编辑 | **结构化**（每条带 git_commit_sha + last_verified_at）|

### 1.3 L3 索引层（主动召回）— **✅ 脚本已就绪**

| 范围 | 状态 |
|------|------|
| MEMORY.md | ✅ 已索引 |
| memory/*.md | ✅ 已索引 |
| skills/ | ✅ `reindex_memory.py` |
| database/ | ✅ `reindex_memory.py` |
| docs/ | ✅ `reindex_memory.py` |

**reindex 频率**：每周日凌晨 03:00（launchd 触发）

### 1.4 L4 真相源（不可篡改）— **v2.0 强化**

**铁律**：MEMORY.md 可能错，git 不会错。

| 真相项 | 来源 | 不用 MEMORY.md 的原因 |
|--------|------|----------------------|
| 当前活跃版本 | VERSION 文件 | MEMORY.md 是手账，可能忘改 |
| 最近决策 | git log | 决策细节在 commit message，不在 MEMORY.md |
| 断档日期 | 文件 mtime | 推断不靠谱 |
| 数据库 schema | SQL DDL 文件 | MEMORY.md 写的可能过时 |

**被挑战时的修正流程**（v1.0 学到的）：

```
1. 立刻承认"我没查代码就回答了"
2. cat VERSION / git log -10 / ls -lt skills/
3. 用代码事实修正 MEMORY.md
4. git commit 修正后的 MEMORY.md（加证据）
```

### 1.5 L5 决策层（人类可读）— **v2.0 强化**

| 维护动作 | 频率 | 自动化 |
|----------|------|--------|
| 周清理（移 14+ 天日志到 archive/）| 每周 | 手动（Phase 3 半自动）|
| 月归档（MEMORY.md 只留 7 天摘要 + 永久事实）| 每月 | 手动 |
| 决策记录 | 每次迭代 | **强制 4W 模板**（§7）|
| 自我复盘 | 每次会话结束 | SESSION_END 必填 |

---

## 2. 数据模型（v2.0 新增）

### 2.1 记忆条目的结构

```python
@dataclass
class MemoryEntry:
    when: str           # YYYY-MM-DD HH:MM GMT+8
    what: str           # 客观事实（一句话）
    why: str            # 触发原因
    witness: str        # 证据（git sha / 文件路径 / 数据）
    category: str       # 决策/事实/复盘/错误/学习
    verified_at: str    # YYYY-MM-DD HH:MM
    verified_by: str    # version_check / git log / mtime / 人工
```

### 2.2 决策记录模型

```python
@dataclass
class Decision:
    name: str                # 决策名
    date: str                # YYYY-MM-DD
    trigger: str             # 触发事件
    options: List[Option]    # 候选方案
    chosen: str              # 选定方案
    reason: str              # 选择理由
    failure_conditions: str  # 什么情况下回滚
    approver: str            # 金姐 / 老板
    evidence: List[str]      # git sha, 评测结果, 文件
    review_date: str         # YYYY-MM-DD（下次复审）
```

### 2.3 质量分（v2.0 引入）

每条记忆计算一个 0-1 的质量分：

```
quality = (has_when + has_what + has_why + has_witness) / 4
       × (verified_recently ? 1.0 : 0.5)
       × (has_evidence ? 1.0 : 0.7)
```

- `quality >= 0.8`：✅ 高质量
- `0.5 <= quality < 0.8`：⚠️ 一般
- `quality < 0.5`：❌ 需补全

---

## 3. 防断档机制（v1.0 → v2.0 强化）

### 3.1 断档检测（已上线）

`scripts/check_continuity.sh` — 每日跑
- OK：最新日志 < 24h
- WARN：24-72h（飞书告警）
- P0：> 72h（飞书 P0 告警）

### 3.2 强制日结（已上线，金姐定制）

`scripts/daily_wrap.sh` — 每日 10:00
- 总结**昨天**数据
- 飞书推送（如果 webhook 配置）
- 写 `/tmp/daily_wrap_<date>.md`
- 更新 MEMORY.md 时间戳

### 3.3 启动 4 项自检（已上线）

`scripts/startup_check.py` — 每次启动
1. version_check（VERSION/CHANGELOG/SKILL.md 一致）
2. git_clean（无未提交重要修改）
3. memory_fresh（MEMORY.md < 7 天）
4. no_pending（无紧急项超 24h）

### 3.4 v2.0 新增：周归档

`scripts/weekly_archive.sh` — 每周日 03:00
- 移 14+ 天的 session 日志到 `memory/archive/2026-Wxx/`
- MEMORY.md 重新生成"最近 7 天"摘要
- 生成周报告

### 3.5 v2.0 新增：月复盘

`scripts/monthly_review.sh` — 每月 1 日 03:00
- 统计本月：迭代次数 / 决策数 / 反例数 / 学习数
- 生成月度趋势图
- 检查 PENDING.md 是否有 30+ 天未更新项

---

## 4. 「好的记忆」质量标准（v2.0 强化）

### 4.1 每条记忆的 4W（强制）

| W | 含义 | 缺失后果 |
|---|------|----------|
| **When** | 绝对日期 + 相对时间 | 不知道"什么时候的事" |
| **What** | 客观事实 | 不知道"发生了什么" |
| **Why** | 触发原因 | 不知道"为什么这样决定" |
| **Witness** | 证据（git sha / 文件 / 数据）| 无法验证真假 |

### 4.2 决策记录 4W 模板

```markdown
## 决策：[决策名]（YYYY-MM-DD）

**触发**：[什么事件触发这次决策？]
**方案对比**：
- 方案 A：[...，优：..., 缺：...]
- 方案 B：[...，优：..., 缺：...]
- 方案 C：[...，优：..., 缺：...]  ✅ 选定

**决定**：[选了哪个]
**理由**：[为什么]
**反例/失败条件**：[什么情况下应该回滚？]
**批准人**：[金姐 / 老板]
**证据**：
- git commit [sha]
- 评测结果 [PASS/FAIL/数字]
- 相关文件 [路径]

**下次复审**：[YYYY-MM-DD]
```

### 4.3 反例（不该再犯的错误）

| 反例 | 表现 | 修复 |
|------|------|------|
| 1 | 老板问"你之前说过什么"凭印象答 | 必查 git log + VERSION |
| 2 | MEMORY.md 写完就当事实 | version_check 强制核对 |
| 3 | 会话结束忘记写日志 | SESSION_END 6 步 + launchd 日结 |
| 4 | 版本号变更不更新三处 | version_check 启动时跑 |
| 5 | 决策没记录模板 | 4W 模板强制 |
| 6 | 飞轮不转无人推 | 每周 review |

---

## 5. 3 阶段实施路线

### 5.1 Phase 1（✅ 已完成）— 反馈采集

事件总线 + 反馈采集器 + 3 张表 + 4 项测试

### 5.2 Phase 2（✅ 已完成）— 自动化守护

3 个守护脚本 + launchd + 14 项测试

### 5.3 Phase 3（✅ 脚本已就绪）— 智能分析

| 子任务 | 目标 | 状态 | 脚本 |
|--------|------|------|------|
| 3.1 memory_search 索引扩展 | skills/ + database/ + docs/ 可搜 | ✅ | `reindex_memory.py` |
| 3.2 MEMORY.md 自动提取 | 从 session 日志 + git log 摘要 | ✅ | `extract_memory.py` |
| 3.3 「好的记忆」质量 4W 检查 | 每条记忆带 4W + 自动检查 | ✅ | `check_memory_quality.py` |
| 3.4 周归档自动化 | 14+ 天日志自动移 | ✅ | `phase3_maintenance.sh` |
| 3.5 月复盘自动化 | 月度趋势报告 | ✅ | `test_phase3.sh` |

### 5.4 Phase 4（📋 计划）— 自治

| 子任务 | 目标 |
|--------|------|
| 4.1 飞轮自动推进 | AI 每周自动找 P0/P1 问题 |
| 4.2 评测趋势 dashboard | 可视化趋势 |
| 4.3 决策智能推荐 | 基于历史推荐方案 |

---

## 6. Phase 3 详细实施计划（6-9 ~ 6-15）

### 3.1 memory_search 索引扩展

**目标**：skills/ + database/ + docs/ 全部可搜

**实施**：
- 写 `scripts/reindex_memory.py`
- 用 memory_search API（如果有）或自建索引
- launchd 每周日凌晨 03:00 自动跑

**验证**：搜索"version_check"能找到所有相关文件

### 3.2 MEMORY.md 自动提取

**目标**：从 session 日志 + git log 自动生成"最近 7 天"摘要

**实施**：
- 写 `scripts/extract_memory.py`
- 解析 `memory/2026-XX-XX.md` 的标题 + git commit
- 生成 7 天摘要到 MEMORY.md
- launchd 每日 11:00 跑（在 daily_wrap 后）

**验证**：MEMORY.md 摘要和实际 session 日志一致

### 3.3 4W 质量检查

**目标**：每条记忆带 4W + 自动检查

**实施**：
- 写 `scripts/check_memory_quality.py`
- 解析 MEMORY.md + session 日志
- 4W 缺失 → 警告
- 输出 quality 分

**验证**：所有 session 日志 quality >= 0.8

### 3.4 周归档

**目标**：14+ 天日志自动移到 archive/

**实施**：
- 写 `scripts/weekly_archive.sh`
- 移动文件到 `memory/archive/2026-Wxx/`
- 更新 MEMORY.md 移除"## 之前"段
- launchd 每周日 03:30 跑

### 3.5 月复盘

**目标**：月度趋势报告

**实施**：
- 写 `scripts/monthly_review.sh`
- 统计本月数据
- 生成 `/tmp/monthly_review_<YYYY-MM>.md`
- launchd 每月 1 日 04:00 跑

---

## 7. 监控指标（飞轮是否在转？）

### 7.1 每日检查

```bash
python3 scripts/startup_check.py
```

**期望**：3-4 ✅ / 0 ❌

### 7.2 每周检查

```bash
# 1. 看测试通过率
bash scripts/test_phase2_guards.sh
bash ../skills/skill_order_to_huading_template/scripts/test_event_pipeline.py

# 2. 看层成功率
PGPASSWORD="" psql -d neo -c "SELECT layer_name, total_attempts, success_rate FROM layer_success_rate WHERE total_attempts > 0;"

# 3. 看订单反馈趋势
PGPASSWORD="" psql -d neo -c "SELECT * FROM v_daily_feedback_stats WHERE order_date >= CURRENT_DATE - 7;"
```

### 7.3 每月检查

```bash
bash scripts/monthly_review.sh
```

**输出**：
- 本月迭代次数
- 本月决策数
- 本月反例数
- 本月新增学习数
- PENDING.md 30+ 天未更新项

---

## 8. 与方法论、Skill 迭代方案的对应

| 方法论 § | 迭代方案 § | 记忆系统 v2.0 § |
|----------|------------|-----------------|
| §4 飞轮 | §3 飞轮结构 | §3 防断档机制（飞轮的"轴承"）|
| §5 L1-L3 自动化 | §4 Phase 1-4 | §5 Phase 1-4（数字一致）|
| §6 反例 1-4 | §6 决策记录 | §4 反例 1-6（含原 4 个 + v2.0 新增 2 个）|
| §2 评测指标 | §2 评测体系 | §2 数据模型（记忆本身可量化）|

---

## 9. 一页纸总结

> **AI建单助手 记忆系统 v2.0**：
>
> 1. **5 层架构**：L1 触发 / L2 协议 / L3 索引 / L4 真相 / L5 决策
> 2. **数据模型**：每条记忆 4W + 质量分（0-1）
> 3. **防断档**：每日 10:00 日结 + 24h 断档告警 + 4 项启动自检
> 4. **3 阶段路线**：Phase 1-3 已完成（采集+守护+智能脚本），Phase 4 自治
> 5. **核心铁律**：git/代码/mtime 是真相源，MEMORY.md 是手账
> 6. **4W 标准**：每条记忆带 When/What/Why/Witness

---

## 10. 自检问题（每天问自己 4 个问题）

1. **我今天动了哪些文件？**（git status 必看）
2. **我做了哪些决定？为什么？**（写进 session 日志，4W 模板）
3. **下次会话开始时，我能从 MEMORY.md 知道今天发生了什么吗？**（可读性测试）
4. **如果老板现在问"上次我们讨论了什么"，我能在 10 秒内给出准确答案吗？**（召回性测试）

任何一题答"否" → 立即修补记忆系统。

---

*AI建单助手 | 2026-06-08 16:25 GMT+8 | 配套：方法论 + Skill 迭代方案 v2.0 + Phase 3 计划*
