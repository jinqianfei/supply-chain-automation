# PENDING — 未完成事项

**最后更新：** 2026-06-10 10:38 GMT+8

---

## 🔴 P1 — 多门店 + 单 confirmed_store 行为错误

**发现时间**：2026-06-10
**复现命令**：
```bash
cd /Users/jinqianfei/openclaw-workspaces/ai-order
echo "0" | python3 tests/manual_e2e.py 2
# 第 1 次 execute 返回 2 个门店（天津塘沽万达 + 北京天宫院）
# 用户只传 1 个 confirmed_store（塘沽万达）
# 第 2 次 execute 返回 success=True，store_names 正确显示 2 个
# 但 Excel 11 行**全部**用 KH2025072100075（塘沽万达的 store_code）
```

**根因**（位置：`__init__.py` line 1785-1797）：
```python
if confirmed_store:
    si = confirmed_store  # ⚠️ 用同一个 confirmed_store 处理所有门店
```

**期望行为**：
- 多门店场景：传 `confirmed_stores: Dict[store_key, store_info]`
- 缺失某门店确认时：返回 `need_store_confirm: True` for that store
- 或：保留单 `confirmed_store` 但仅对单门店订单生效

**影响范围**：
- 单门店订单：✅ 不受影响
- 多门店订单：❌ 第 2 起门店的 store_code 错用第 1 个

**建议方案**（v5.12.0 候选）：
1. 把 `execute()` 的 `confirmed_store` 参数改 `confirmed_stores: Dict[store_key, Dict]`
2. 多门店循环内按 store_key 查 confirmed_stores
3. 未确认的门店返回 need_store_confirm + 已确认门店的部分结果

**预计工作量**：30 分钟（含测试）

---

## 🟡 P2 — 4 个 git tag 未推 remote（含 v5.12.0）

**发现时间**：2026-06-10（持续 blocker）

**现状**（2026-06-10 12:13 确认）：
```bash
$ git tag -l
v5.9.0-baseline
v5.11.0
v5.11.2
v5.12.0
# 全部本地，未推 remote
```

**为何不推**：
- skill 的 git repo（`skills/skill_order_to_huading_template/.git`）**没有任何 remote 配置**
- 父级 `/Users/jinqianfei` 仓库的 remote 是 `github/jinqianfei/supply-chain-automation` 和 `huggingface/jinqianfei/green-light-go`（不是 skill 专属）
- 金姐未明确指定 push 目标

**待金姐决定**（3 选 1）：
- **B-1**：给 skill 加 github remote（需 URL + token）→ 我推 4 tag
- **B-2**：tag 留本地（当前默认）→ 已记入本文件
- **B-3**：把 skill git 合并到父级 `/Users/jinqianfei` 仓库

**风险**：不推 remote → 其他机器 / 协作者看不到 tag + commit

**应急方案**：如需立即在其他机器使用，可 `git clone /Users/jinqianfei/openclaw-workspaces/ai-order/skills/skill_order_to_huading_template` 本地拷贝

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

**改造工作量评估**：
1. `db/connection.py` 加驱动抽象层（psycopg2 / pymysql 自动切换）：0.5 天
2. 6 处 `psycopg2.connect()` 改为抽象连接：0.5 天
3. `ANY(%s)` → `IN (...)`：10 分钟
4. `learn/` 模块的 3 处 PG 语法：1 小时
5. `learn/schema.sql` 加 MySQL 版本：1 小时
6. 测试验证：0.5 天
7. **合计：约 2 天**

**不需要改的部分**：
- 核心业务 SQL（95%+）都是标准 SQL（SELECT/WHERE/ORDER BY/LIKE/INSERT/UPDATE）
- 参数化查询 `%s` 占位符（MySQL 的 pymysql 也用 `%s`）

**实施建议**：
- 优先级：P2（当前 PostgreSQL 运行正常，无紧迫需求）
- 触发条件：金姐决定部署到 MySQL 环境时再执行
- 预估版本：v5.14.0 或 v5.15.0

---

## ✅ 已完成（本次会话）

- [x] 5 个版本 5 commit 提交（v5.9.0 / 5.11.0 / 5.11.1 / 5.11.2 / 5.10.0 文档补）
- [x] git tag v5.11.2 + 修 v5.11.0 tag
- [x] 完整代码审计（9 文件 ~6000 行）
- [x] 写 `tests/manual_e2e.py` 手动测试脚本
- [x] 端到端真实订单回归（#1 洪洪通 + #2 天津仓 = 12/12 GT 准确率）
- [x] v5.11.1 quantity 修复验证（多门店场景也生效）
- [x] daily log `memory/2026-06-10.md` 写完
- [x] 主 `MEMORY.md` 最近会话摘要段更新
- [x] `memory/projects/ai-order/PROJECT.md` 升级到 v5.11.2
- [x] 本 PENDING.md 建立
- [x] **P1 bug 修复**（v5.12.0 commit `1dfb57c`）：多门店 + 单 confirmed_store 正确处理
- [x] **2 个新回归测试**：test_execute_confirmation_flow.py + test_execute_import_fallback.py
- [x] **git tag v5.12.0** 打 tag → 1dfb57c
- [x] 4 个 tag 状态更新到 PENDING.md（默认 B-2 留本地，等金姐决定）

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
- 数据库 15MB，23张表，5个 GIN trgm 索引
- Cloudflare Tunnel 临时 URL

**阿里云目标配置**：
- ECS: ecs.c6.xlarge (4核8G), 40GB SSD → ¥200-300/月
- RDS PG: 1核2G 基础版, PG 16 → ¥100-150/月
- 同地域同 VPC，内网延迟 < 1ms
- 总月费：¥330-500

**执行步骤**：
1. Phase 0: 购买 ECS + RDS（控制台操作）
2. Phase 1: ECS 环境搭建（Node.js/Python/OpenClaw/cloudflared/Redis，~30min）
3. Phase 2: pg_dump → pg_restore 数据库迁移（停机 < 5min）
4. Phase 3: rsync 工作区同步 + .env 改 DB_HOST（~10min）
5. Phase 4: 启动 Gateway + Cloudflare Tunnel（~10min）
6. Phase 5: 端到端验证（~15min）
7. Phase 6: 交付 + 7天观察期

**需要金姐做的**：
1. 购买阿里云 ECS + RDS PostgreSQL
2. 提供 ECS IP + SSH 密码 + RDS 内网地址

**关键兼容项**：
- pg_trgm 扩展：阿里云 RDS PG 支持，需先 CREATE EXTENSION
- PG 版本：当前 18.3 → 阿里云 16/17，pg_dump -F c 向下兼容

**触发条件**：金姐决定迁移时启动
