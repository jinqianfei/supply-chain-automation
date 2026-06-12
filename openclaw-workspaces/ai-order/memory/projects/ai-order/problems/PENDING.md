# PENDING — 未完成事项

**最后更新：** 2026-06-12 10:32 GMT+8

---

## ✅ 已完成 — P1 多门店 confirmed_store bug（v5.15.2 修复）

**发现时间**：2026-06-10
**修复时间**：2026-06-12（v5.15.2）

**原问题**：
- 多门店场景 + 单 confirmed_store → 第 2 门店 store_code 错用第 1 门店
- 位置：`__init__.py` line 1785-1797

**修复内容**：
- 新增 `_call_match_store` 对比逻辑
- 用户选的 ≠ 系统匹配时才 emit `store_corrected`
- 单门店 + 多门店两条路径都修复
- v5.12.0 首次修复 → v5.15.2 进一步完善（store_corrected 误触发修复）

**状态**：✅ 已修复 + 测试通过

---

## 🟡 P2 — 自学习闭环需要数据积累

**发现时间**：2026-06-12
**当前状态**：等待数据积累

**问题**：
- `order_corrections` 表 0 条数据
- 原因：19 单全是单门店，用户从未纠正过（真实数据）
- 自学习闭环（采集→分析→改进）需要纠正数据才能触发分析→改进循环

**当前可做的**：
- ✅ 采集器 10/10 事件全覆盖
- ✅ 分析脚本就绪（analyze_learning_data.py + accuracy_comparison.py）
- ✅ 历史回放脚本就绪（history_replay.py）
- ⏳ 等待真实用户纠正数据积累

**触发条件**：用户纠正门店/SKU 匹配时自动写入 order_corrections

**预计**：当累积 ≥ 10 条纠正数据时，可首次运行分析脚本生成改进建议

---

## 🟡 P2 — 记忆模块 Phase 4（自治）未开始

**发现时间**：2026-06-12
**当前状态**：pending

**Phase 1~3 状态**：
- ✅ Phase 1：事件总线 + 反馈采集器（v5.9.0）
- ✅ Phase 2：日结脚本 + launchd 定时器 + 启动自检
- ✅ Phase 3：脚本已就绪（memory quality check / reindex / extract）

**Phase 4（自治）目标**：
- AI 自动执行 session start/end 协议
- AI 自动检测断档并补写日志
- AI 自动更新 PROJECT.md / PENDING.md
- 减少人工干预（金姐不需要手动触发）

**预计工作量**：2~3 天（需要重新设计 AI 行为协议）

**触发条件**：金姐决定启动时执行

---

## 🟡 P2 — `mapping_table` 字段返回为空

**发现时间**：2026-06-10
**复现**：跑 `tests/manual_e2e.py` 1 或 2 时，response["review_data"]["mapping_table"] = []
**代码位置**：`__init__._generate_mapping_comparison_multi`（line 3218）
**影响**：UI 想展示"SKU 映射对照表"时取不到数据（但不影响 Excel 生成）
**建议**：调 `_generate_mapping_comparison_multi` 看实际返回什么字段名

---

## 🟡 P2 — 数据库兼容性改造（支持 MySQL）

**发现时间**：2026-06-10
**当前状态**：pending（暂不执行）

**需求背景**：
- 当前代码仅支持 PostgreSQL（AWS RDS）
- 用户询问是否需要支持 MySQL 环境
- 评估结论：可行，核心 SQL 不用动

**PostgreSQL 特有依赖盘点**：
1. `psycopg2` 驱动（6处）：`db/connection.py`、`_sku_mapper.py`、`_store_matcher.py`、`__init__.py`、`learn/collector.py`、`test_event_pipeline.py`
2. `ANY(%s)` 数组操作符（1处）：`__init__.py:2725`
3. `SERIAL` 自增列（3处）：`learn/schema.sql`
4. `ON CONFLICT ... DO NOTHING`（2处）：`learn/collector.py`
5. `RETURNING id`（1处）：`learn/collector.py:264`
6. GIN trgm 索引（数据库层面，不在代码里）

**改造工作量评估**：约 2 天

**实施建议**：
- 优先级：P2（当前 PostgreSQL 运行正常，无紧迫需求）
- 触发条件：金姐决定部署到 MySQL 环境时再执行

---

## 🟡 P2 — AWS EC2 → 阿里云 ECS 全量迁移（方案 C）

**发现时间**：2026-06-10
**当前状态**：pending（暂不执行，方案已定稿）

**方案文档**：
- 本地：`docs/阿里云迁移方案.md`
- 飞书：https://feishu.cn/docx/GGaXdGCTUocIqdxrno7cdP7tnPc

**推荐方案 C：计算 + 数据库一起迁**

**当前 AWS 架构**：
- EC2 (13.212.17.85, 新加坡) + RDS PostgreSQL 18.3 (新加坡)
- 数据库 15MB，23张表，7个 GIN trgm 索引
- Cloudflare Tunnel 临时 URL

**阿里云目标配置**：
- ECS: ecs.c6.xlarge (4核8G), 40GB SSD → ¥200-300/月
- RDS PG: 1核2G 基础版, PG 16 → ¥100-150/月
- 同地域同 VPC，内网延迟 < 1ms
- 总月费：¥330-500

**触发条件**：金姐决定迁移时启动

---

## 🟡 P2 — 记忆模块 P1~P6 修复收尾

**发现时间**：2026-06-12
**当前状态**：部分完成，需收尾

**6-12 发现的 7 个问题**：
1. P1: SESSION_END_PROTOCOL.md 未包含 v5.15.x 的新步骤
2. P2: check_continuity.sh 断档检测阈值过宽
3. P3: daily_wrap.sh 报告格式需更新
4. P4: startup_check.py 缺少自学习模块检查
5. P5: MEMORY_SYSTEM_PLAN.md Phase 4（自治）未开始
6. P6: 记忆质量评分脚本 check_memory_quality.py 需优化
7. P7: 部分文档交叉引用断链

**状态**：P1~P6 并行执行中，部分已完成

---

## ✅ 已完成（历史）

- [x] 5 个版本 5 commit 提交（v5.9.0 ~ v5.11.2 + v5.10.0 文档补）— 6-10
- [x] git tag v5.9.0-baseline / v5.11.0 / v5.11.2 / v5.12.0 — 6-10
- [x] 完整代码审计（9 文件 ~6000 行）— 6-10
- [x] 端到端真实订单回归 12/12 GT 准确率 — 6-10
- [x] P1 bug 修复（v5.12.0 commit `1dfb57c`）— 6-10
- [x] 2 个新回归测试 — 6-10
- [x] git push 到 github — 6-10
- [x] 自学习模块 review + 补齐 6 个缺失 EventBus.emit — 6-11
- [x] v5.13.3 修复：果糖末尾孤立分隔符 — 6-11
- [x] CI 回归测试建立（53/53 全过）— 6-11
- [x] v5.14.0 修复：单位匹配逻辑 — 6-11
- [x] 端到端测试 85/85 = 100% 准确率 — 6-11
- [x] 自学习闭环 review（方案标注虚高修正）— 6-12
- [x] order_corrections 0 条诊断 — 6-12
- [x] 补 3 个缺失组件（DB列 + history_replay + accuracy_comparison）— 6-12
- [x] v5.15.2 发布（store_corrected 误触发修复）— 6-12
- [x] 硬编码全修（P1~P4 + launchd plist × 3）— 6-12
- [x] config/analysis_config.yaml 统一管理 8 处阈值 — 6-12
- [x] 记忆模块方案 review（20 项扫描，7 个问题）— 6-12
- [x] git push 成功（工作区 + skill 仓库 HTTPS）— 6-12
