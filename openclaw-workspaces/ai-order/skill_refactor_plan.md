# AI建单助手 — 模块化拆分方案（实战修正版）

> 基于当前 v5.16.0 稳定版本 + 飞书工程化方案 + 自学习/记忆模块解耦需求
> 
> 原则：**小改不大改，自学习完全解耦，保持 AI 可读性，解决真实痛点**
> 
> 日期：2026-06-12

---

## 1. 现状评估

### 1.1 当前架构（v5.16.0）

```
skills/skill_order_to_huading_template/
├── SKILL.md                    # AI 指令文档（4000+行）
├── __init__.py                 # 主入口类（186KB，4000+行）
├── tools/
│   ├── order_parser.py         # Step 1: 订单解析
│   └── field_transformer.py    # Step 2: 字段标准化
├── learn/                      # ⚠️ 自学习模块（耦合在 skill 内）
│   ├── collector.py            # 订阅事件 → 写数据库
│   ├── adapter.py              # payload → DB record
│   ├── schema.sql              # 建表 SQL
│   └── llm/                    # LLM 调用层（6个文件）
├── events/
│   └── bus.py                  # 事件总线
├── field_mapping/
│   └── rules/{客户名}.yaml     # 字段映射规则
└── output/
```

### 1.2 当前架构的优点（必须保留）

| 优点 | 说明 |
|------|------|
| 6步流水线清晰 | parse → transform → match_store → match_sku → generate → send |
| 3次调用铁律 | AI 严格按 3 次 execute() 调用，不多不少 |
| 钉钉文件发送铁律 | message 工具发原生文件卡片，禁止 MEDIA: |
| AI 防跳过规范 | 禁止跳过 execute() 直接调用内部方法 |
| 多门店支持 | confirmed_stores 字典结构，门店→货主→SKU 全链路 |
| 人工确认点 | 门店匹配和 SKU 映射都必须用户确认 |

### 1.3 当前架构的痛点

| 痛点 | 影响 | 严重程度 |
|------|------|----------|
| **自学习模块耦合在 skill 内** | 改学习逻辑要动 skill 主文件，学习模块挂了影响 skill | ⭐⭐⭐⭐⭐ |
| **SQL 散落在方法内部** | 改一个查询要改方法代码，容易引入 bug | ⭐⭐⭐ |
| **模糊匹配逻辑重复** | store_matcher 和 sku_matcher 各写一套相似度计算 | ⭐⭐ |
| **用户纠正逻辑嵌在 skill 内** | _parse_user_feedback / _apply_modifications 无法独立迭代 | ⭐⭐⭐ |
| **无独立测试目录** | 测试用例散落，无法独立运行 | ⭐ |
| **无连接管理** | 每次调用重新连数据库，无连接池/重连 | ⭐ |

---

## 2. 拆分目标

1. **自学习/记忆模块完全解耦** — skill 只管发事件，不管谁订阅
2. **SQL 集中管理** — 所有查询集中到 queries.py
3. **模糊匹配复用** — 提取为共享工具
4. **核心逻辑拆模块** — 单文件 186KB → 多模块各司其职
5. **保持所有铁律不变** — 3次调用、钉钉发送、AI防跳过

---

## 3. 目标架构

### 3.1 Skill 本体（纯业务逻辑）

```
skills/skill_order_to_huading_template/
├── SKILL.md                        # AI 指令文档（保持不变）
├── __init__.py                     # 主入口（精简为编排层，~300行）
│
├── core/                           # 【新增】核心业务逻辑
│   ├── __init__.py
│   ├── store_matcher.py            # Step 3: 门店匹配（6层+2兜底）
│   ├── sku_matcher.py              # Step 4: SKU匹配（5层）
│   └── generator.py                # Step 5: Excel生成（31字段）
│
├── db/                             # 【新增】数据库层
│   ├── __init__.py
│   ├── connection.py               # 连接管理（连接复用 + 自动重连）
│   └── queries.py                  # SQL 查询集中管理
│
├── utils/                          # 【新增】共享工具
│   ├── __init__.py
│   └── fuzzy_match.py              # 模糊匹配算法（门店/SKU 共用）
│
├── tools/                          # 解析 + 转换（保持不变）
│   ├── order_parser.py
│   └── field_transformer.py
│
├── field_mapping/
│   └── rules/{客户名}.yaml         # 字段映射规则（保持不变）
│
└── output/                         # 生成的 Excel 文件（保持不变）
```

### 3.2 工作区级独立模块（从 skill 内移出）

```
workspace/
├── learning/                       # 【独立】自学习系统
│   ├── __init__.py
│   ├── collector.py                # 订阅事件 → 写数据库
│   ├── adapter.py                  # payload → DB record 转换
│   ├── feedback_parser.py          # 【从 skill 移出】用户纠正解析
│   ├── modifier.py                 # 【从 skill 移出】修改应用逻辑
│   ├── schema.sql                  # 学习数据建表 SQL
│   └── llm/                        # LLM 调用层
│       ├── __init__.py
│       ├── router.py
│       ├── provider.py
│       ├── openai.py
│       ├── openai_compat.py
│       ├── openclaw.py
│       └── custom_http.py
│
├── events/                         # 【独立】事件总线
│   ├── __init__.py
│   └── bus.py                      # 极简事件总线（纯路由，不存储）
│
└── skills/
    └── skill_order_to_huading_template/   # ← Skill 本体（上面 3.1）
```

### 3.3 模块依赖关系

```
┌─────────────────────────────────────────────────────┐
│            __init__.py (编排层，~300行)               │
│     OrderToHuadingTemplate.execute()                 │
│     + EventBus.emit() × 11处（只发事件）              │
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
 │    workspace/events/bus.py   │  ← Skill 通过 sys.path 引用
 │    （事件总线，纯路由）        │     只 import EventBus
 └──────────┬───────────────────┘
            │ handler 订阅
 ┌──────────▼───────────────────┐
 │  workspace/learning/          │  ← 完全独立
 │  collector.py + adapter.py    │     自行初始化
 │  feedback_parser.py           │     不依赖 skill 代码
 │  modifier.py                  │
 │  llm/                         │
 └──────────────────────────────┘
```

**依赖规则**：
- Skill → db/ → utils/（上层依赖下层）
- Skill → events/bus.py（只 import，不 import learning）
- learning → events/bus.py（订阅事件）
- **learning 不依赖 skill 的任何代码**
- **skill 不 import learning 的任何模块**

---

## 4. 自学习/记忆模块解耦方案（核心改动）

### 4.1 当前耦合点

`__init__.py` 中与自学习相关的代码：

| 代码 | 位置 | 问题 |
|------|------|------|
| `from learning.collector import init_feedback_collector` | 第30行 | skill 直接 import 学习模块 |
| `init_feedback_collector(self.db_config)` | 第1758行 | skill 负责启动学习模块 |
| `EventBus.emit("store_confirmed", ...)` | 第1941行 | 发事件（✅ 保留） |
| `EventBus.emit("store_corrected", ...)` | 第1954行 | 发事件（✅ 保留） |
| `EventBus.emit("store_confirm_needed", ...)` | 第2057行 | 发事件（✅ 保留） |
| `EventBus.emit("sku_confirm_needed", ...)` | 第2300行 | 发事件（✅ 保留） |
| `EventBus.emit("sku_corrected", ...)` | 第2444行 | 发事件（✅ 保留） |
| `EventBus.emit("sku_confirmed", ...)` | 第2466行 | 发事件（✅ 保留） |
| `EventBus.emit("order_complete", ...)` | 第2529行 | 发事件（✅ 保留） |
| `EventBus.emit("user_modified", ...)` | 第3712行 | 发事件（✅ 保留） |
| `def _parse_user_feedback()` | 第3586行 | ~150行，用户纠正解析逻辑 |
| `def _apply_modifications()` | 第3741行 | ~70行，修改应用逻辑 |

### 4.2 解耦方式

**保留的**（skill 内）：
- 11处 `EventBus.emit()` — skill 只负责"喊一嗓子"
- `order_data_cache` — 这是业务状态，跨调用传递，不是记忆
- `order_session_id` — 会话追踪 ID，业务需要

**移出的**（移到 workspace/learning/）：
- `from learning.collector import ...` → 删除这行 import
- `init_feedback_collector(self.db_config)` → 删除，learning 自行启动
- `def _parse_user_feedback()` → 移到 `workspace/learning/feedback_parser.py`
- `def _apply_modifications()` → 移到 `workspace/learning/modifier.py`
- `learn/` 整个目录 → 移到 `workspace/learning/`
- `events/bus.py` → 移到 `workspace/events/bus.py`

### 4.3 解耦后的调用流程

```
用户确认门店 "是的，就用廖朵朵-徐州沛县"
    │
    ▼
Skill: EventBus.emit("store_confirmed", {
    "store_name": "廖朵朵-徐州沛县",
    "owner_code": "HZ2024091100001",
    "match_method": "包含匹配",
    ...
})
    │
    │  ← Skill 到这里就结束了，不知道谁在听
    │
    ▼
EventBus (workspace/events/bus.py)
    │ 路由到所有 handler
    ▼
Learning Collector (workspace/learning/collector.py)
    │ adapter.transform(data) → DB record
    │ db.insert(record)
    ▼
Database (learning_feedback 表)
```

### 4.4 用户纠正流程（解耦后）

当前：用户说"把A改成B" → skill 内 `_parse_user_feedback()` 解析 → `_apply_modifications()` 应用

解耦后：
```
用户说 "把A改成B"
    │
    ▼
Skill: 检测到是修改指令
    │ EventBus.emit("user_feedback", {"raw_text": "把A改成B", ...})
    │ 
    │ 同时：调用 workspace/learning/feedback_parser.py 解析修改
    │ 返回：modifications = [{"field": "sku", "from": "A", "to": "B"}]
    │
    │ 应用修改到当前映射结果
    ▼
继续流程...
```

**关键**：`feedback_parser.py` 和 `modifier.py` 是独立模块，skill 通过函数调用使用它们，但它们不 import skill 的任何代码。

---

## 5. 各模块详细设计

### 5.1 db/connection.py — 连接管理

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

### 5.2 db/queries.py — SQL 集中管理

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

### 5.3 utils/fuzzy_match.py — 模糊匹配工具

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

### 5.4 core/store_matcher.py — 门店匹配

```python
class StoreMatcher:
    def __init__(self, db: DBConnection):
        self.db = db
    
    def match(self, store_name, phone, address, contact_person, owner_code) -> dict:
        """6层匹配 + 2兜底，返回匹配结果 + candidates"""
    
    def get_candidates(self, store_name, owner_code) -> list:
        """获取候选门店列表"""
```

### 5.5 core/sku_matcher.py — SKU 匹配

```python
class SKUMatcher:
    def __init__(self, db: DBConnection):
        self.db = db
    
    def match(self, product_name, shipper_id, spec) -> dict:
        """5层匹配，返回匹配结果"""
    
    def match_batch(self, items, shipper_id) -> dict:
        """批量匹配，返回 {sku_results, unmatched_items}"""
```

### 5.6 core/generator.py — Excel 生成

```python
class TemplateGenerator:
    def __init__(self, db: DBConnection):
        self.db = db
    
    def generate(self, order_data, all_store_results) -> str:
        """生成31字段出库单 Excel，返回文件路径"""
```

### 5.7 __init__.py — 主入口（精简为编排层）

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

## 6. 分步实施计划

### Phase 1：基础层（15分钟）

| 步骤 | 操作 | 风险 |
|------|------|------|
| 1.1 | 创建 `db/` 目录 | 无 |
| 1.2 | 实现 `db/connection.py`（连接复用 + 重连） | 低 |
| 1.3 | 实现 `db/queries.py`（从现有代码提取所有 SQL） | 低 |
| 1.4 | 验证：独立执行查询 | 无 |

**验收**：`python -c "from db.connection import DBConnection; ..."` 通过

### Phase 2：工具层（10分钟）

| 步骤 | 操作 | 风险 |
|------|------|------|
| 2.1 | 创建 `utils/` 目录 | 无 |
| 2.2 | 实现 `utils/fuzzy_match.py`（从 store_matcher/sku_matcher 提取） | 低 |
| 2.3 | 验证：相似度计算正确 | 无 |

**验收**：单元测试通过

### Phase 3：服务层（20分钟）

| 步骤 | 操作 | 风险 |
|------|------|------|
| 3.1 | 创建 `core/` 目录 | 无 |
| 3.2 | 实现 `core/store_matcher.py`（从 `__init__.py` 抽出 `_match_store`） | 中 |
| 3.3 | 实现 `core/sku_matcher.py`（从 `__init__.py` 抽出 `_match_sku`） | 中 |
| 3.4 | 实现 `core/generator.py`（从 `__init__.py` 抽出 `_generate_template`） | 中 |
| 3.5 | 验证：每个模块独立可测试 | 无 |

**验收**：各模块独立 import + 运行通过

### Phase 4：自学习解耦（15分钟）

| 步骤 | 操作 | 风险 |
|------|------|------|
| 4.1 | 将 `learn/` 目录移到 `workspace/learning/` | 低 |
| 4.2 | 将 `events/bus.py` 移到 `workspace/events/` | 低 |
| 4.3 | 将 `_parse_user_feedback()` 移到 `workspace/learning/feedback_parser.py` | 中 |
| 4.4 | 将 `_apply_modifications()` 移到 `workspace/learning/modifier.py` | 中 |
| 4.5 | 删除 `__init__.py` 中的 `from learning.collector import ...` | 低 |
| 4.6 | 删除 `init_feedback_collector(self.db_config)` 调用 | 低 |
| 4.7 | 保留 11处 `EventBus.emit()`（只发事件） | 低 |
| 4.8 | learning 模块自行初始化（独立启动脚本或 cron） | 中 |

**验收**：
- skill 内 `grep -r "learning" .` 无结果（除了 EventBus.emit）
- skill 内 `grep -r "collector" .` 无结果
- 端到端流程正常，事件仍能写入数据库

### Phase 5：编排层 + 端到端测试（15分钟）

| 步骤 | 操作 | 风险 |
|------|------|------|
| 5.1 | 重写 `__init__.py` 为纯编排层（~300行） | 中 |
| 5.2 | 保留 3次调用铁律 | 低 |
| 5.3 | 保留钉钉文件发送铁律 | 低 |
| 5.4 | 端到端测试：完整订单处理流程 | 高 |

**验收**：用真实订单测试，3次调用后生成正确 Excel，钉钉发送成功

### Phase 6：测试层（10分钟）

| 步骤 | 操作 | 风险 |
|------|------|------|
| 6.1 | 创建 `tests/` 目录 | 无 |
| 6.2 | 编写 `test_fuzzy_match.py` | 低 |
| 6.3 | 编写 `test_store_matcher.py` | 低 |
| 6.4 | 编写 `test_sku_matcher.py` | 低 |
| 6.5 | 编写 `test_generator.py` | 低 |

**验收**：`pytest tests/` 全部通过

**总计：约 85 分钟**

---

## 7. 验收标准

### 7.1 功能验收

- [ ] 3次调用流程正常（门店确认 → SKU确认 → 生成发送）
- [ ] 多门店订单正确处理
- [ ] 钉钉原生文件卡片发送成功
- [ ] 所有匹配逻辑与重构前一致（回归测试通过）
- [ ] 用户纠正门店/SKU 功能正常
- [ ] 事件仍能写入学习数据库（collector 独立运行正常）

### 7.2 架构验收

- [ ] skill 内 `grep -r "learning\|collector\|feedback_parser" .` 无结果
- [ ] skill 内不 import learning 的任何模块
- [ ] 每个模块可独立导入和测试
- [ ] SQL 全部集中在 db/queries.py
- [ ] 模糊匹配逻辑只存在于 utils/fuzzy_match.py
- [ ] 依赖方向正确（上层→下层，无反向依赖）
- [ ] learning 模块不 import skill 的任何代码

### 7.3 性能验收

- [ ] 连接复用：第2次调用不重新建连
- [ ] 处理速度无明显下降（< 5% 差异）

---

## 8. 风险与回滚

### 8.1 风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| SQL 提取遗漏 | 中 | 功能缺失 | 逐条对比原代码 SQL |
| 自学习解耦后事件丢失 | 中 | 学习数据不写入 | learning 独立启动 + 验证 emit 仍生效 |
| 用户纠正流程断裂 | 中 | 用户说"改A为B"无效 | feedback_parser 独立测试 |
| 模块接口不兼容 | 低 | 调用失败 | 保持 execute() 接口不变 |

### 8.2 回滚方案

重构前备份：
- `__init__.py` → `__init__.py.bak`
- `learn/` → `learn.bak/`
- `events/` → `events.bak/`

如果重构后端到端测试失败，恢复备份即可回滚。

---

## 9. 不做的事

明确列出**不实施**的项，避免过度工程化：

- ❌ 不做 ORM / models.py — SQL 集中管理已足够
- ❌ 不做 config/settings.py — os.getenv() 够用
- ❌ 不做重量级连接池 — 连接复用 + 重连即可
- ❌ 不拆分 SKILL.md — AI 需要完整流程文档
- ❌ 不改变 6 步流水线 — 核心业务逻辑
- ❌ 不改变 3 次调用铁律 — 用户反复验证的规则
- ❌ 不改变钉钉文件发送铁律
- ❌ 不在 skill 内保留 learn/ 目录 — 完全移出

---

## 10. 与飞书方案对比

| 维度 | 飞书方案 | 本方案（实战修正版） |
|------|---------|-------------------|
| 自学习解耦 | ❌ 完全没提 | ✅ learn/ 移出 + 事件解耦 + feedback_parser 独立 |
| 用户纠正逻辑 | ❌ 没提 | ✅ 移到 workspace/learning/ |
| 事件总线 | ❌ 没提 | ✅ 移到 workspace/events/ |
| SQL 集中 | ✅ queries.py | ✅ queries.py |
| 模糊匹配复用 | ✅ fuzzy_match.py | ✅ fuzzy_match.py |
| 核心模块拆分 | core/ 5文件 | core/ 3文件（更精简） |
| 配置管理 | 独立 config/ | 保持 os.getenv() |
| 数据模型 | 独立 models.py | 不需要 |
| 钉钉发送铁律 | ❌ 未体现 | ✅ 保留 |
| 3次调用铁律 | ❌ 未体现 | ✅ 保留 |
| AI 防跳过 | ❌ 未体现 | ✅ 保留 |
| 实施风险 | 高（全面重写） | 中（渐进式重构） |

---

## 11. 总结

本方案的核心思路：

> **保持 AI 友好的单入口架构，把"工程债"和"耦合债"一起拆出来。**

**拆什么**：
- SQL → `db/queries.py`
- 模糊匹配 → `utils/fuzzy_match.py`
- 核心逻辑 → `core/` 三个模块
- 连接管理 → `db/connection.py`
- **自学习模块 → `workspace/learning/`（完全解耦）**
- **事件总线 → `workspace/events/`（独立部署）**
- **用户纠正逻辑 → `workspace/learning/feedback_parser.py`**

**不拆什么**：
- SKILL.md（AI 需要完整文档）
- 6步流水线（核心业务）
- 3次调用铁律（用户验证的规则）
- 钉钉发送铁律（渠道规则）
- AI防跳过规范（安全规则）
- order_data_cache（业务状态，不是记忆）

**一句话**：这不是"推翻重来"，而是"在稳定基础上做微创手术，同时把自学习这个寄生虫摘干净"。
