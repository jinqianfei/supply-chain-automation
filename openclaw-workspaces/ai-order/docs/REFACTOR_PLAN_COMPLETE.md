# AI建单助手 — 完整重构方案

> **基于实战修正版 + 记忆模块/运维脚本/launchd 三项补充**
>
> **版本**：v1.0 | **日期**：2026-06-12
>
> **原则**：小改不大改，自学习完全解耦，保持 AI 可读性，解决真实痛点
>
> **基础版本**：v5.16.0 稳定版

---

## 1. 现状评估

### 1.1 当前架构

```
skills/skill_order_to_huading_template/
├── SKILL.md                    # AI 指令文档（4000+行）
├── __init__.py                 # 主入口类（186KB，4153行）
├── tools/
│   ├── _order_parser.py        # Step 1: 订单解析
│   ├── _field_transformer.py   # Step 2: 字段标准化
│   ├── _store_matcher.py       # Step 3: 门店匹配
│   ├── _sku_mapper.py          # Step 4: SKU匹配
│   └── _template_generator.py  # Step 5: Excel生成
├── learn/                      # ⚠️ 自学习模块（耦合在 skill 内）
│   ├── collector.py            # 订阅事件 → 写数据库
│   ├── adapter.py              # payload → DB record
│   ├── schema.sql              # 建表 SQL
│   └── llm/                    # LLM 调用层（6个文件）
├── events/
│   └── bus.py                  # 事件总线
├── db/
│   └── connection.py           # 数据库连接
├── config/
│   ├── db_config.yaml
│   ├── llm.yaml
│   └── template_defaults.yaml
├── field_mapping/
│   └── rules/{客户名}.yaml     # 字段映射规则
└── output/                     # 生成的 Excel 文件
```

**工作区层面**：

```
workspace/
├── scripts/                    # ⚠️ 混杂（自学习+记忆+运维，共25个文件）
│   ├── analyze_learning_data.py    (自学习)
│   ├── daily_alias_summary.py      (自学习)
│   ├── notification_sender.py      (自学习)
│   ├── check_memory_quality.py     (记忆)
│   ├── extract_memory.py           (记忆)
│   ├── reindex_memory.py           (记忆)
│   ├── startup_check.py            (记忆+Skill)
│   ├── history_replay.py           (自学习)
│   ├── accuracy_comparison.py      (自学习)
│   ├── daily_wrap.sh               (运维)
│   ├── check_continuity.sh         (运维)
│   ├── auto_git_skill.sh           (运维)
│   ├── deploy_to_aliyun.sh         (运维)
│   └── ...（还有11个运维脚本）
│
├── config/                     # ⚠️ 自学习配置散放
│   ├── analysis_config.yaml
│   └── notification_config.yaml
│
├── launchd/                    # ⚠️ 定时任务（路径引用 scripts/）
│   ├── com.ai-order.daily-wrap.plist
│   ├── com.ai-order.daily-alias-summary.plist
│   └── com.ai-order.phase3-maintenance.plist
│
├── memory/                     # ⚠️ 协议文档和运行时数据混在一起
│   ├── SESSION_START_PROTOCOL.md
│   ├── SESSION_END_PROTOCOL.md
│   ├── PENDING_PROTOCOL.md
│   ├── MEMORY_SYSTEM_PLAN.md
│   ├── 2026-06-*.md           (运行时日志)
│   └── projects/              (运行时数据)
│
└── docs/ / data/ / output/     # 保留不动
```

### 1.2 痛点汇总

| # | 痛点 | 严重程度 | 来源 |
|---|------|---------|------|
| 1 | **`__init__.py` 4153行** — 核心逻辑全堆在一个文件 | ⭐⭐⭐⭐⭐ | 实战方案 |
| 2 | **自学习模块耦合在 skill 内** — 改学习逻辑要动主文件 | ⭐⭐⭐⭐⭐ | 实战方案 |
| 3 | **SQL 散落在方法内部** — 改一个查询要改方法代码 | ⭐⭐⭐ | 实战方案 |
| 4 | **模糊匹配逻辑重复** — store_matcher 和 sku_matcher 各写一套 | ⭐⭐ | 实战方案 |
| 5 | **scripts/ 混杂** — 自学习/记忆/运维25个文件混在一起 | ⭐⭐⭐ | 补充方案 |
| 6 | **记忆协议散落** — 协议文档和运行时数据混在一起 | ⭐⭐ | 补充方案 |
| 7 | **launchd 路径耦合** — 定时任务硬编码 scripts/ 路径 | ⭐⭐ | 补充方案 |
| 8 | **无独立测试目录** — 测试用例散落 | ⭐ | 实战方案 |
| 9 | **无连接管理** — 每次调用重新连数据库 | ⭐ | 实战方案 |

### 1.3 必须保留的铁律

| 铁律 | 说明 |
|------|------|
| **6步流水线** | parse → transform → match_store → match_sku → generate → send |
| **3次调用铁律** | AI 严格按 3 次 execute() 调用，不多不少 |
| **钉钉文件发送铁律** | message 工具发原生文件卡片，禁止 MEDIA: |
| **AI 防跳过规范** | 禁止跳过 execute() 直接调用内部方法 |
| **多门店支持** | confirmed_stores 字典结构，门店→货主→SKU 全链路 |
| **人工确认点** | 门店匹配和 SKU 映射都必须用户确认 |

---

## 2. 目标架构

### 2.1 完整目标结构

```
ai-order/                                        # 工作区根目录
│
├── AGENTS.md / SOUL.md / IDENTITY.md / ...     # Agent 配置（保留）
├── MEMORY.md / TOOLS.md / .env                  # 工作区配置（保留）
│
├── skills/
│   └── skill_order_to_huading_template/         # 订单映射 Skill
│       ├── SKILL.md                             # AI 指令文档（不动）
│       ├── __init__.py                          # 编排层（~300行，精简）
│       │
│       ├── core/                                # 🆕 核心业务逻辑
│       │   ├── __init__.py
│       │   ├── store_matcher.py                 # Step 3: 门店匹配（6层+2兜底）
│       │   ├── sku_matcher.py                   # Step 4: SKU匹配（5层）
│       │   └── generator.py                     # Step 5: Excel生成（31字段）
│       │
│       ├── db/                                  # 🆕 数据库层
│       │   ├── __init__.py
│       │   ├── connection.py                    # 连接管理（复用+重连）
│       │   └── queries.py                       # SQL 集中管理
│       │
│       ├── utils/                               # 🆕 共享工具
│       │   ├── __init__.py
│       │   └── fuzzy_match.py                   # 模糊匹配算法（门店/SKU 共用）
│       │
│       ├── tools/                               # 解析+转换（保留）
│       │   ├── _order_parser.py
│       │   └── _field_transformer.py
│       │
│       ├── config/                              # Skill 配置（保留）
│       │   ├── db_config.yaml
│       │   ├── llm.yaml
│       │   └── template_defaults.yaml
│       │
│       ├── field_mapping/                       # 字段映射规则（保留）
│       │   └── rules/{客户名}.yaml
│       │
│       ├── tests/                               # 🆕 Skill 测试
│       │   ├── test_fuzzy_match.py
│       │   ├── test_store_matcher.py
│       │   ├── test_sku_matcher.py
│       │   ├── test_generator.py
│       │   ├── test_p1_multi_store_fix.py
│       │   └── test_sku_mapper_regression.py
│       │
│       ├── VERSION / CHANGELOG.md
│       └── output/                              # 生成的 Excel
│
├── learning/                                    # 🆕 独立自学习系统
│   ├── __init__.py
│   ├── collector.py                             # 订阅事件 → 写数据库
│   ├── adapter.py                               # payload → DB record
│   ├── feedback_parser.py                       # 用户纠正解析（从 skill 移出）
│   ├── modifier.py                              # 修改应用逻辑（从 skill 移出）
│   ├── schema.sql                               # 学习数据建表 SQL
│   ├── scripts/
│   │   ├── analyze_data.py                      # 数据分析
│   │   ├── daily_summary.py                     # 每日别名汇总
│   │   ├── notification_sender.py               # 通知发送
│   │   ├── history_replay.py                    # 历史回放
│   │   └── accuracy_comparison.py               # 准确率对比
│   ├── config/
│   │   ├── analysis_config.yaml                 # 分析阈值
│   │   └── notification_config.yaml             # 通知配置
│   └── llm/                                     # LLM 调用层
│       ├── __init__.py
│       ├── router.py
│       ├── provider.py
│       ├── openai.py
│       ├── openai_compat.py
│       ├── openclaw.py
│       └── custom_http.py
│
├── events/                                      # 🆕 独立事件总线
│   ├── __init__.py
│   └── bus.py                                   # 极简事件总线（纯路由）
│
├── memory_system/                               # 🆕 记忆系统（补充）
│   ├── protocols/
│   │   ├── SESSION_START_PROTOCOL.md
│   │   ├── SESSION_END_PROTOCOL.md
│   │   └── PENDING_PROTOCOL.md
│   ├── scripts/
│   │   ├── check_quality.py                     # 记忆质量检查
│   │   ├── extract_memory.py                    # 记忆提取
│   │   ├── reindex.py                           # 记忆索引
│   │   └── startup_check.py                     # 启动自检
│   └── templates/
│       └── PROJECT_TEMPLATE.md
│
├── ops/                                         # 🆕 运维脚本（补充）
│   ├── daily_wrap.sh                            # 每日日结
│   ├── check_continuity.sh                      # 断档检测
│   ├── auto_git_skill.sh                        # Git 自动提交
│   ├── deploy_to_aliyun.sh                      # 阿里云部署
│   ├── sync_to_aliyun.sh                        # 同步阿里云
│   ├── sync_to_ec2.sh                           # 同步 EC2
│   ├── setup_agent.sh                           # Agent 初始化
│   ├── install_launchd.sh                       # launchd 安装
│   ├── export_db_for_migration.py               # DB 导出
│   ├── run_migrations.sh                        # 数据库迁移
│   ├── weekly_archive.sh                        # 周归档
│   ├── monthly_review.sh                        # 月度回顾
│   ├── phase3_maintenance.sh                    # Phase 3 维护
│   └── ci_regression.sh                         # CI 回归测试入口
│
├── launchd/                                     # launchd 配置（更新路径）
│   ├── com.ai-order.daily-wrap.plist
│   ├── com.ai-order.daily-alias-summary.plist
│   └── com.ai-order.phase3-maintenance.plist
│
├── memory/                                      # 运行时数据（仅保留运行时产物）
│   ├── MEMORY_SYSTEM_PLAN.md                    # 方案文档（保留）
│   ├── 2026-06-*.md                             # 日志
│   ├── projects/ai-order/                       # 项目记忆
│   └── archive/                                 # 归档
│
├── scripts/                                     # 精简后只保留 CI 相关
│   └── test_sku_mapper_regression.py            # SKU 回归测试数据
│
└── docs/ / data/ / output/                      # 保留不动
```

### 2.2 依赖关系

```
┌─────────────────────────────────────────────────────┐
│         __init__.py (编排层，~300行)                  │
│    OrderToHuadingTemplate.execute()                  │
│    + EventBus.emit() × 11处（只发事件）               │
└──────┬──────────┬──────────┬────────────────────────┘
       │          │          │
 ┌─────▼───┐ ┌───▼────┐ ┌──▼──────────┐
 │ tools/  │ │ core/  │ │ core/       │
 │ parser  │ │ store_ │ │ sku_matcher │
 │ trans-  │ │matcher │ │ generator   │
 │ former  │ │        │ │             │
 └────┬────┘ └───┬────┘ └──┬──────────┘
      │          │         │
 ┌────▼──────────▼─────────▼────┐
 │           db/                 │
 │  connection.py + queries.py   │
 └──────────┬───────────────────┘
            │
 ┌──────────▼───────────────────┐
 │          utils/               │
 │      fuzzy_match.py          │
 └──────────────────────────────┘

 ===== 以上全部在 skill 内 =====
 ===== 以下全部在 skill 外 =====

 ┌──────────────────────────────┐
 │    events/bus.py             │  ← Skill 通过 sys.path 引用
 │    （事件总线，纯路由）        │     只 import EventBus
 └──────────┬───────────────────┘
            │ handler 订阅
 ┌──────────▼───────────────────┐
 │  learning/                    │  ← 完全独立
 │  collector.py + adapter.py    │     自行初始化
 │  feedback_parser.py           │     不依赖 skill 代码
 │  modifier.py                  │
 │  llm/                         │
 └──────────────────────────────┘

 ┌──────────────────────────────┐
 │  memory_system/              │  ← 完全独立
 │  protocols/ + scripts/       │     被 AGENTS.md 引用
 └──────────────────────────────┘

 ┌──────────────────────────────┐
 │  ops/                        │  ← 完全独立
 │  运维脚本 + launchd 路径引用  │     不依赖任何 Python 模块
 └──────────────────────────────┘
```

**依赖规则**：
- Skill → db/ → utils/（上层依赖下层）
- Skill → events/bus.py（只 import EventBus，不 import learning）
- learning → events/bus.py（订阅事件）
- memory_system 独立运行（被 AGENTS.md 协议引用）
- ops 独立运行（shell 脚本，不 import Python 模块）
- **learning 不依赖 skill 的任何代码**
- **skill 不 import learning 的任何模块**

---

## 3. Skill 内部重构详细设计

### 3.1 db/connection.py — 连接管理

```python
class DBConnection:
    def __init__(self, db_config: dict):
        self.config = db_config
        self._conn = None
    
    def get_connection(self):
        """获取连接（优先复用，失败重连，最多3次）"""
    
    def execute_query(self, sql: str, params: tuple = None) -> list:
        """执行查询，返回结果列表"""
    
    def execute_one(self, sql: str, params: tuple = None) -> dict:
        """执行查询，返回单条结果"""
    
    def close(self):
        """关闭连接"""
```

### 3.2 db/queries.py — SQL 集中管理

```python
# ============ 门店匹配 SQL ============
STORE_MATCH_BY_PHONE = "SELECT ... FROM store_list WHERE phone = %s LIMIT 1"
STORE_MATCH_BY_NAME = "SELECT ... FROM store_list WHERE store_name = %s LIMIT 1"
STORE_MATCH_BY_NAME_LIKE = "SELECT ... WHERE store_name ILIKE %s ..."
STORE_MATCH_BY_OWNER = "SELECT ... WHERE owner_code = %s ..."
STORE_MATCH_BY_CONTACT = "SELECT ... WHERE contact_person = %s ..."

# ============ SKU 匹配 SQL ============
SKU_MATCH_EXACT = "SELECT ... FROM product_sku WHERE shipper_id = %s AND ..."
SKU_MATCH_LIKE = "SELECT ... WHERE shipper_id = %s AND sku_name ILIKE %s ..."
SKU_MATCH_KEYWORD = "SELECT ... WHERE shipper_id = %s AND ..."
ALIAS_MATCH = "SELECT ... FROM product_name_alias a JOIN product_sku s ..."

# ============ 仓库/货主 SQL ============
WAREHOUSE_CODE_BY_STORE = "SELECT ... FROM warehouse_code_mapping ..."
CUSTOMER_BY_OWNER_CODE = "SELECT ... FROM customer WHERE owner_code = %s"
```

### 3.3 utils/fuzzy_match.py — 模糊匹配工具

```python
def calculate_similarity(s1: str, s2: str) -> float:
    """计算两个字符串的相似度（0-1）"""

def extract_keywords(name: str, top_n: int = 5) -> list:
    """提取关键词（前N字 + 后N字）"""

def best_match(candidates: list, target: str, key: str = 'name') -> dict:
    """从候选列表中找出最佳匹配"""

def filter_by_threshold(candidates: list, target: str, threshold: float,
                        key: str = 'name') -> list:
    """按相似度阈值过滤候选列表"""
```

### 3.4 core/store_matcher.py — 门店匹配

```python
class StoreMatcher:
    def __init__(self, db: DBConnection):
        self.db = db
    
    def match(self, store_name, phone, address, contact_person, owner_code) -> dict:
        """6层匹配 + 2兜底，返回匹配结果 + candidates"""
    
    def get_candidates(self, store_name, owner_code) -> list:
        """获取候选门店列表"""
```

### 3.5 core/sku_matcher.py — SKU 匹配

```python
class SKUMatcher:
    def __init__(self, db: DBConnection):
        self.db = db
    
    def match(self, product_name, shipper_id, spec) -> dict:
        """5层匹配，返回匹配结果"""
    
    def match_batch(self, items, shipper_id) -> dict:
        """批量匹配，返回 {sku_results, unmatched_items}"""
```

### 3.6 core/generator.py — Excel 生成

```python
class TemplateGenerator:
    def __init__(self, db: DBConnection):
        self.db = db
    
    def generate(self, order_data, all_store_results) -> str:
        """生成31字段出库单 Excel，返回文件路径"""
```

### 3.7 __init__.py — 主入口（精简为编排层）

```python
class OrderToHuadingTemplate:
    __public_api__ = ['execute']  # AI 只能调用这个
    
    def __init__(self, db_config=None):
        self.db = DBConnection(db_config)
        self.parser = OrderParser()
        self.transformer = FieldTransformer()
        self.store_matcher = StoreMatcher(self.db)
        self.sku_matcher = SKUMatcher(self.db)
        self.generator = TemplateGenerator(self.db)
    
    def execute(self, order_input, order_type, order_data_cache,
                confirmed_store, confirmed_sku) -> dict:
        """
        3次调用铁律状态机：
        第1次：解析 → 标准化 → 门店匹配 → need_store_confirm
        第2次：SKU匹配 → need_sku_confirm
        第3次：生成Excel → 发送钉钉 → success
        """
```

---

## 4. 自学习解耦详细设计

### 4.1 当前耦合点

| 代码 | 位置 | 处理方式 |
|------|------|---------|
| `from learning.collector import init_feedback_collector` | __init__.py 第30行 | ❌ 删除 |
| `init_feedback_collector(self.db_config)` | __init__.py 第1758行 | ❌ 删除 |
| `EventBus.emit("store_confirmed", ...)` | 11处 | ✅ 保留 |
| `def _parse_user_feedback()` | __init__.py ~第3586行 | ➡️ 移到 learning/ |
| `def _apply_modifications()` | __init__.py ~第3741行 | ➡️ 移到 learning/ |

### 4.2 解耦后的初始化机制（软加载）

**问题**：如果 skill 完全不 import learning，谁来初始化 collector 订阅事件？

**方案 A（采纳）：try/except 软加载**

```python
# __init__.py 编排层（~300行中的一段）
class OrderToHuadingTemplate:
    def __init__(self, db_config=None):
        # ... 初始化 db/parser/matcher/generator ...
        
        # 软加载自学习模块（失败不影响主流程）
        self._learning_enabled = False
        try:
            from learning import auto_init
            auto_init(self.db.get_connection_config())
            self._learning_enabled = True
        except ImportError:
            logger.debug("自学习模块未安装，跳过学习功能")
```

**效果**：
- ✅ Skill 不硬依赖 learning（import 失败不报错，订单处理正常）
- ✅ learning 可以随时卸载（删掉目录即可降级）
- ✅ 触发时机和现在完全一样（__init__ 时订阅事件）
- ✅ 解耦的是代码逻辑，不是启动时机

**方案 B/C（不采纳）**：
- B. OpenClaw 启动 hook — 需要 OpenClaw 支持，增加外部依赖
- C. 首次 emit 懒加载 — 需改 EventBus，引入新复杂度

### 4.3 解耦后的事件流

```
Skill __init__
    │
    ▼
try: from learning import auto_init
     auto_init(db_config)
     → collector 订阅 10 个事件
    │
    ▼
用户确认门店
    │
    ▼
Skill: EventBus.emit("store_confirmed", {...})
    │  ← Skill 到这里就结束了
    ▼
EventBus (events/bus.py)
    │ 路由到所有 handler
    ▼
Learning Collector (learning/collector.py)
    │ adapter.transform(data) → DB record
    ▼
Database (order_feedback / order_corrections / layer_success_rate)
```

### 4.4 用户纠正流程（解耦后）

```
用户说 "把A改成B"
    │
    ▼
Skill: 检测到修改指令
    │ 调用 learning/feedback_parser.py 解析
    │ 返回：modifications = [{"field": "sku", "from": "A", "to": "B"}]
    │ 调用 learning/modifier.py 应用修改
    ▼
继续流程...
```

**关键**：feedback_parser.py 和 modifier.py 不 import skill 的任何代码，skill 通过函数调用使用它们。

---

## 5. 记忆模块提取详细设计（补充）

### 5.1 移动清单

| 源文件 | 目标文件 |
|-------|---------|
| `memory/SESSION_START_PROTOCOL.md` | `memory_system/protocols/SESSION_START_PROTOCOL.md` |
| `memory/SESSION_END_PROTOCOL.md` | `memory_system/protocols/SESSION_END_PROTOCOL.md` |
| `memory/PENDING_PROTOCOL.md` | `memory_system/protocols/PENDING_PROTOCOL.md` |
| `memory/projects/PROJECT_TEMPLATE.md` | `memory_system/templates/PROJECT_TEMPLATE.md` |
| `scripts/check_memory_quality.py` | `memory_system/scripts/check_quality.py` |
| `scripts/extract_memory.py` | `memory_system/scripts/extract_memory.py` |
| `scripts/reindex_memory.py` | `memory_system/scripts/reindex.py` |

### 5.2 startup_check.py 拆分

当前 `scripts/startup_check.py` 同时做 4 件事：
1. version_check — VERSION/SKILL.md/CHANGELOG 三处一致（Skill 相关）
2. git_clean — 无未提交的重要文件（通用）
3. memory_fresh — MEMORY.md 距今 < 7 天（记忆相关）
4. no_pending — PENDING.md 无紧急项超 24h（记忆相关）

**拆分方案**：
- 检查 1（version_check）→ 保留在 `ops/ci_regression.sh` 中（已有 `version_check.sh`）
- 检查 2/3/4 → `memory_system/scripts/startup_check.py`
- 原 `scripts/startup_check.py` → 改为薄壳，调用上面两部分

### 5.3 memory/ 目录保留内容

```
memory/                            # 只保留运行时数据
├── MEMORY_SYSTEM_PLAN.md          # 方案文档（保留参考）
├── 2026-06-*.md                   # 日志（运行时产物）
├── projects/ai-order/             # 项目记忆（运行时产物）
└── archive/                       # 归档
```

### 5.4 AGENTS.md 路径更新

```markdown
# 改造前
每次结束会话时必须执行：
1. 执行 `memory/SESSION_END_PROTOCOL.md`

# 改造后
每次结束会话时必须执行：
1. 执行 `memory_system/protocols/SESSION_END_PROTOCOL.md`
```

---

## 6. 运维脚本整理详细设计（补充）

### 6.1 移动清单

| 源文件 | 目标文件 | 说明 |
|-------|---------|------|
| `scripts/daily_wrap.sh` | `ops/daily_wrap.sh` | 每日日结 |
| `scripts/check_continuity.sh` | `ops/check_continuity.sh` | 断档检测 |
| `scripts/auto_git_skill.sh` | `ops/auto_git_skill.sh` | Git 自动提交 |
| `scripts/deploy_to_aliyun.sh` | `ops/deploy_to_aliyun.sh` | 阿里云部署 |
| `scripts/sync_to_aliyun.sh` | `ops/sync_to_aliyun.sh` | 同步阿里云 |
| `scripts/sync_to_ec2.sh` | `ops/sync_to_ec2.sh` | 同步 EC2 |
| `scripts/setup_agent.sh` | `ops/setup_agent.sh` | Agent 初始化 |
| `scripts/install_launchd.sh` | `ops/install_launchd.sh` | launchd 安装 |
| `scripts/export_db_for_migration.py` | `ops/export_db_for_migration.py` | DB 导出 |
| `scripts/run_migrations.sh` | `ops/run_migrations.sh` | 数据库迁移 |
| `scripts/weekly_archive.sh` | `ops/weekly_archive.sh` | 周归档 |
| `scripts/monthly_review.sh` | `ops/monthly_review.sh` | 月度回顾 |
| `scripts/phase3_maintenance.sh` | `ops/phase3_maintenance.sh` | Phase 3 维护 |
| `scripts/test_phase2_guards.sh` | `ops/test_phase2_guards.sh` | Phase 2 测试 |
| `scripts/test_phase3.sh` | `ops/test_phase3.sh` | Phase 3 测试 |

### 6.2 自学习脚本移动

| 源文件 | 目标文件 |
|-------|---------|
| `scripts/analyze_learning_data.py` | `learning/scripts/analyze_data.py` |
| `scripts/daily_alias_summary.py` | `learning/scripts/daily_summary.py` |
| `scripts/notification_sender.py` | `learning/scripts/notification_sender.py` |
| `scripts/history_replay.py` | `learning/scripts/history_replay.py` |
| `scripts/accuracy_comparison.py` | `learning/scripts/accuracy_comparison.py` |

### 6.3 scripts/ 精简后保留

```
scripts/
└── test_sku_mapper_regression.py   # SKU 回归测试（Skill 相关）
```

### 6.4 内部路径更新

`ops/daily_wrap.sh` 内部路径更新：
```bash
# 改造前
SCRIPTS_DIR="$WORKSPACE/scripts"

# 改造后
OPS_DIR="$WORKSPACE/ops"
LEARNING_DIR="$WORKSPACE/learning/scripts"
MEMORY_DIR="$WORKSPACE/memory_system/scripts"
```

---

## 7. launchd 更新详细设计（补充）

### 7.1 plist 路径更新

**com.ai-order.daily-wrap.plist**：
```xml
<!-- 改造前 -->
<string>/Users/jinqianfei/openclaw-workspaces/ai-order/scripts/daily_wrap.sh</string>

<!-- 改造后 -->
<string>/Users/jinqianfei/openclaw-workspaces/ai-order/ops/daily_wrap.sh</string>
```

**com.ai-order.daily-alias-summary.plist**：
```xml
<!-- 改造前 -->
<string>python3</string>
<string>/Users/jinqianfei/openclaw-workspaces/ai-order/scripts/daily_alias_summary.py</string>

<!-- 改造后 -->
<string>python3</string>
<string>/Users/jinqianfei/openclaw-workspaces/ai-order/learning/scripts/daily_summary.py</string>
```

**com.ai-order.phase3-maintenance.plist**：
```xml
<!-- 改造前 -->
<string>/Users/jinqianfei/openclaw-workspaces/ai-order/scripts/phase3_maintenance.sh</string>

<!-- 改造后 -->
<string>/Users/jinqianfei/openclaw-workspaces/ai-order/ops/phase3_maintenance.sh</string>
```

### 7.2 重新安装

```bash
# 改造后执行
bash ops/install_launchd.sh
# 验证
launchctl list | grep ai-order
```

---

## 8. 分步实施计划

### Phase 1：基础层（15分钟）

| 步骤 | 操作 | 风险 |
|------|------|------|
| 1.1 | 创建 `skills/.../db/` 目录 | 无 |
| 1.2 | 实现 `db/connection.py`（连接复用 + 重连） | 低 |
| 1.3 | 实现 `db/queries.py`（从现有代码提取所有 SQL） | 低 |
| 1.4 | 验证：独立执行查询 | 无 |

**验收**：`python -c "from db.connection import DBConnection; ..."` 通过

### Phase 2：工具层（10分钟）

| 步骤 | 操作 | 风险 |
|------|------|------|
| 2.1 | 创建 `skills/.../utils/` 目录 | 无 |
| 2.2 | 实现 `utils/fuzzy_match.py`（从 store_matcher/sku_matcher 提取） | 低 |
| 2.3 | 验证：相似度计算正确 | 无 |

**验收**：单元测试通过

### Phase 3：服务层（20分钟）

| 步骤 | 操作 | 风险 |
|------|------|------|
| 3.1 | 创建 `skills/.../core/` 目录 | 无 |
| 3.2 | 实现 `core/store_matcher.py`（从 `__init__.py` 抽出 `_match_store`） | 中 |
| 3.3 | 实现 `core/sku_matcher.py`（从 `__init__.py` 抽出 `_match_sku`） | 中 |
| 3.4 | 实现 `core/generator.py`（从 `__init__.py` 抽出 `_generate_template`） | 中 |
| 3.5 | 验证：每个模块独立可测试 | 无 |

**验收**：各模块独立 import + 运行通过

### Phase 4：自学习解耦（15分钟）

| 步骤 | 操作 | 风险 |
|------|------|------|
| 4.1 | 将 `skills/.../learn/` 移到 `learning/` | 低 |
| 4.2 | 将 `skills/.../events/bus.py` 移到 `events/` | 低 |
| 4.3 | 将 `_parse_user_feedback()` 移到 `learning/feedback_parser.py` | 中 |
| 4.4 | 将 `_apply_modifications()` 移到 `learning/modifier.py` | 中 |
| 4.5 | 删除 `__init__.py` 中的硬 import，改为 try/except 软加载 | 低 |
| 4.6 | 在 `learning/__init__.py` 中实现 `auto_init()` 函数 | 低 |
| 4.7 | 保留 11处 `EventBus.emit()`（只发事件） | 低 |
| 4.8 | 验证：无 learning 目录时 Skill 仍能正常处理订单 | 中 |

**验收**：
- skill 内 `grep -r "from learning" .` 只有 try/except 软加载（无硬 import）
- skill 内 `grep -r "collector\|feedback_parser" .` 无结果
- 端到端流程正常，事件仍能写入数据库
- 临时移除 learning/ 目录后，Skill 仍能正常处理订单（降级模式）

### Phase 5：编排层精简 + 端到端测试（15分钟）

| 步骤 | 操作 | 风险 |
|------|------|------|
| 5.1 | 重写 `__init__.py` 为纯编排层（~300行） | 中 |
| 5.2 | 保留 3次调用铁律 | 低 |
| 5.3 | 保留钉钉文件发送铁律 | 低 |
| 5.4 | 端到端测试：完整订单处理流程 | 高 |

**验收**：用真实订单测试，3次调用后生成正确 Excel，钉钉发送成功

### Phase 6：记忆模块提取（25分钟）🆕

| 步骤 | 操作 | 风险 |
|------|------|------|
| 6.1 | 创建 `memory_system/protocols/` + `scripts/` + `templates/` | 无 |
| 6.2 | 移动 3 个协议文档到 `memory_system/protocols/` | 低 |
| 6.3 | 移动 PROJECT_TEMPLATE.md 到 `memory_system/templates/` | 低 |
| 6.4 | 移动 3 个记忆脚本到 `memory_system/scripts/` | 低 |
| 6.5 | 拆分 `startup_check.py`（Skill 部分 vs 记忆部分） | 中 |
| 6.6 | 更新 AGENTS.md / MEMORY.md 中的路径引用 | 低 |
| 6.7 | 验证：记忆质量检查脚本正常运行 | 低 |

**验收**：
- `python3 memory_system/scripts/check_quality.py` 通过
- AGENTS.md 中路径引用正确

### Phase 7：运维脚本整理 + launchd 更新（20分钟）🆕

| 步骤 | 操作 | 风险 |
|------|------|------|
| 7.1 | 创建 `ops/` 目录 | 无 |
| 7.2 | 移动 15 个运维脚本到 `ops/` | 低 |
| 7.3 | 移动 5 个自学习脚本到 `learning/scripts/` | 低 |
| 7.4 | 移动 2 个配置文件到 `learning/config/` | 低 |
| 7.5 | 更新 `ops/daily_wrap.sh` 内部路径引用 | 中 |
| 7.6 | 更新 3 个 launchd plist 路径 | 中 |
| 7.7 | 执行 `bash ops/install_launchd.sh` 重新安装 | 低 |
| 7.8 | 验证：`launchctl list \| grep ai-order` 正常 | 低 |

**验收**：
- `bash ops/daily_wrap.sh --no-feishu` 正常执行
- `launchctl list | grep ai-order` 3 个任务都在
- `grep -r "scripts/" launchd/` 无旧路径残留

### Phase 8：Skill 测试 + 全面回归（15分钟）

| 步骤 | 操作 | 风险 |
|------|------|------|
| 8.1 | 创建 `skills/.../tests/` 目录 | 无 |
| 8.2 | 编写 `test_fuzzy_match.py` | 低 |
| 8.3 | 编写 `test_store_matcher.py` | 低 |
| 8.4 | 编写 `test_sku_matcher.py` | 低 |
| 8.5 | 编写 `test_generator.py` | 低 |
| 8.6 | 运行 CI 回归（53/53） | 低 |
| 8.7 | 端到端真实订单测试（1单门店 + 1多门店） | 中 |

**验收**：
- `pytest tests/` 全部通过
- CI 53/53 通过
- 真实订单端到端跑通

---

## 9. 验收标准汇总

### 9.1 功能验收

- [ ] 3次调用流程正常（门店确认 → SKU确认 → 生成发送）
- [ ] 多门店订单正确处理
- [ ] 钉钉原生文件卡片发送成功
- [ ] 所有匹配逻辑与重构前一致（CI 53/53 通过）
- [ ] 用户纠正门店/SKU 功能正常
- [ ] 事件仍能写入学习数据库（collector 独立运行正常）

### 9.2 架构验收

- [ ] skill 内 `grep -r "learning\|collector\|feedback_parser" .` 无结果
- [ ] skill 内只有 try/except 软加载 learning（无硬 import）
- [ ] 移除 learning/ 后 Skill 仍能正常运行（降级验证）
- [ ] 每个模块可独立导入和测试
- [ ] SQL 全部集中在 db/queries.py
- [ ] 模糊匹配逻辑只存在于 utils/fuzzy_match.py
- [ ] 依赖方向正确（上层→下层，无反向依赖）
- [ ] learning 模块不 import skill 的任何代码
- [ ] memory_system/ 协议文档完整
- [ ] ops/ 脚本完整，scripts/ 只剩 CI 测试
- [ ] launchd plist 路径全部指向新位置

### 9.3 铁律验收

- [ ] 3次调用铁律不变
- [ ] 钉钉文件发送铁律不变
- [ ] AI 防跳过规范不变
- [ ] 6步流水线不变
- [ ] 多门店 confirmed_stores 结构不变
- [ ] 人工确认点不变

### 9.4 性能验收

- [ ] 连接复用：第2次调用不重新建连
- [ ] 处理速度无明显下降（< 5% 差异）

---

## 10. 风险与回滚

### 10.1 风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| SQL 提取遗漏 | 中 | 功能缺失 | 逐条对比原代码 SQL |
| 自学习解耦后事件丢失 | 中 | 学习数据不写入 | learning 独立启动 + 验证 emit 仍生效 |
| 用户纠正流程断裂 | 中 | 用户说"改A为B"无效 | feedback_parser 独立测试 |
| 模块接口不兼容 | 低 | 调用失败 | 保持 execute() 接口不变 |
| launchd 路径失效 | 中 | 定时任务不执行 | Phase 7 重新安装 + 验证 |
| AGENTS.md 路径断裂 | 低 | AI 行为异常 | 全文 grep 旧路径 + 替换 |
| memory/ 运行时数据误删 | 低 | 日志丢失 | 只移动协议文档，不移动运行时数据 |

### 10.2 回滚方案

重构前备份：
```bash
# 全量备份
tar -czf backups/pre_refactor_$(date +%Y%m%d_%H%M%S).tar.gz \
    skills/skill_order_to_huading_template/ \
    scripts/ config/ launchd/ memory/

# 关键文件单备
cp skills/.../__init__.py skills/.../__init__.py.bak
cp -r skills/.../learn/ skills/.../learn.bak/
cp -r skills/.../events/ skills/.../events.bak/
```

如果重构后端到端测试失败，恢复备份即可回滚。

---

## 11. 不做的事

- ❌ 不做 ORM / models.py — SQL 集中管理已足够
- ❌ 不做 config/settings.py — os.getenv() 够用
- ❌ 不做重量级连接池 — 连接复用 + 重连即可
- ❌ 不拆分 SKILL.md — AI 需要完整流程文档
- ❌ 不改变 6 步流水线 — 核心业务逻辑
- ❌ 不改变 3 次调用铁律
- ❌ 不改变钉钉文件发送铁律
- ❌ 不在 skill 内保留 learn/ 目录 — 完全移出
- ❌ 不改数据库结构
- ❌ 不拆分 tools/（parser + transformer 已够清晰）
- ❌ 不做成 pip install 包 — 等有复用需求时再做
- ❌ 不迁移到阿里云 — 重构完成后再考虑

---

## 12. 实施时间线

| Phase | 内容 | 预计耗时 | 风险 |
|-------|------|---------|------|
| **Phase 1** | db/ 层（连接管理 + SQL 集中） | 15分钟 | 低 |
| **Phase 2** | utils/ 层（模糊匹配复用） | 10分钟 | 低 |
| **Phase 3** | core/ 层（store + sku + generator） | 20分钟 | 中 |
| **Phase 4** | 自学习解耦（learn/ → learning/） | 15分钟 | 中 |
| **Phase 5** | 编排层精简 + 端到端测试 | 15分钟 | 高 |
| **Phase 6** | 记忆模块提取 | 25分钟 | 低 |
| **Phase 7** | 运维脚本整理 + launchd 更新 | 20分钟 | 中 |
| **Phase 8** | Skill 测试 + 全面回归 | 15分钟 | 低 |
| **总计** | | **~2.5小时** | |

---

*文档结束 — 等待金姐确认后开始执行*
