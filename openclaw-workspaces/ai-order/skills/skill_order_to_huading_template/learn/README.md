# AI建单助手自适应学习系统 Phase 1
# Feedback Collector — 反馈采集层

> **功能：** 在每次订单处理的关键节点记录用户反馈数据，
> 为后续 Pattern Extraction、Adaptive Matching、Self-Healing 提供数据基础。

---

## 模块清单

```
learn/
├── __init__.py                  # 主入口
├── feedback_collector.py         # 反馈采集核心
├── schema.sql                    # 数据库表
└── README.md                     # 使用说明
```

---

## 关键采集点

| 触发时机 | 采集内容 | 写入表 |
|---------|---------|--------|
| 门店确认（用户选门店） | 原始名称、选中门店、匹配层、匹配分数 | `order_feedback` |
| SKU确认（用户确认/修改SKU） | 原始SKU、最终SKU、匹配层、分数、修改字段 | `order_feedback` |
| 模板生成（用户确认生成） | 处理时长、订单类型、门店数、SKU总数、匹配率 | `order_feedback` |
| 用户修改字段 | 修改类型、原始值、用户值、修改数量 | `order_corrections` |
| 订单完成 | 完整记录写入 | `order_feedback` |

---

## 数据表设计

### order_feedback（订单处理反馈主表）

```sql
CREATE TABLE order_feedback (
    id SERIAL PRIMARY KEY,
    session_id TEXT,
    order_date DATE,
    order_type TEXT,               -- excel / image / pdf / word / text
    store_count INT,
    sku_count INT,
    matched_store_count INT,
    matched_sku_count INT,
    store_match_rate FLOAT,
    sku_match_rate FLOAT,
    user_confirmed BOOLEAN,        -- 用户最终确认
    user_modified BOOLEAN,         -- 用户有修改门店或SKU
    corrections JSONB,             -- [{type, original, corrected, layer, score}]
    modifications JSONB,           -- [{row, field, old_value, new_value}]
    processing_time_ms INT,
    skill_version TEXT,
    owner_code TEXT,               -- 货主ID
    source_file TEXT,               -- 来源文件路径
    alerts JSONB,                  -- 告警列表
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_feedback_order_date ON order_feedback(order_date);
CREATE INDEX idx_feedback_skill_version ON order_feedback(skill_version);
CREATE INDEX idx_feedback_owner ON order_feedback(owner_code);
```

### order_corrections（用户纠正记录）

```sql
CREATE TABLE order_corrections (
    id SERIAL PRIMARY KEY,
    feedback_id INT REFERENCES order_feedback(id),
    correction_type TEXT,          -- store / sku / unit / quantity / spec
    entity_name TEXT,              -- 被纠正的实体名称
    original_value TEXT,
    corrected_value TEXT,
    match_layer TEXT,              -- 用第几层匹配到的
    match_score FLOAT,
    auto_matched BOOLEAN,          -- 是否自动匹配后被纠正
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_corrections_feedback ON order_corrections(feedback_id);
CREATE INDEX idx_corrections_type ON order_corrections(correction_type);
```

### layer_success_rate（匹配层成功率统计）

```sql
CREATE TABLE layer_success_rate (
    id SERIAL PRIMARY KEY,
    entity_type TEXT,              -- store / sku
    layer_name TEXT,               -- layer_1 / layer_2 / layer_3 ...
    layer_description TEXT,        -- 层的说明
    total_attempts INT DEFAULT 0,
    success_count INT DEFAULT 0,  -- 用户直接确认（未修改）
    auto_success_count INT DEFAULT 0,  -- 自动确认（相似度>=90%）
    user_corrected_count INT DEFAULT 0,  -- 被用户纠正
    success_rate FLOAT DEFAULT 0,
    avg_match_score FLOAT DEFAULT 0,
    updated_at TIMESTAMP DEFAULT NOW()
);
```

---

## 使用方式

### 在 Skill 现有流程中嵌入

```python
from learn.feedback_collector import FeedbackCollector

# 初始化
collector = FeedbackCollector(db_config)

# 1. 门店确认时记录
collector.record_store_match(
    session_id=session_id,
    order_store_name="制茶青年",        # 用户输入的门店名
    matched_store={"store_name": "制茶青年(旗舰店)", "store_code": "S001"},
    match_layer="layer_2",             # 第2层（前缀/后缀）
    match_score=0.85,
    user_confirmed=True,               # 用户直接确认
    user_selected_from_candidates=True # 用户从候选列表选了
)

# 2. SKU确认时记录
collector.record_sku_match(
    feedback_id=123,
    original={"product_name": "鱼你幸福青花椒酱料", "sku_code": ""},
    final={"product_name": "鱼你幸福青花椒酱料（新款）", "sku_code": "SKU001"},
    match_layer="layer_3",             # 别名层匹配到
    match_score=0.72,
    user_confirmed=False,              # 用户修改了
    user_changed_field="sku_code"     # 修改了sku_code字段
)

# 3. 订单完成时记录
collector.record_order_complete(
    session_id=session_id,
    order_type="excel",
    store_count=5,
    sku_count=23,
    matched_store_count=4,
    matched_sku_count=21,
    store_match_rate=0.80,
    sku_match_rate=0.91,
    user_confirmed=True,
    user_modified=True,               # 有修改（门店或SKU）
    corrections=[...],                 # 从 record_sku_match 累积
    processing_time_ms=4523,
    skill_version="5.8.0",
    owner_code="HZ001",
    source_file="/path/to/order.xlsx"
)

# 4. 更新层成功率（每次匹配后调用）
collector.update_layer_stats(
    entity_type="store",
    layer_name="layer_2",
    match_score=0.85,
    user_confirmed=False  # 被纠正了
)

# 5. 查询统计
stats = collector.get_layer_stats("sku")
# {'layer_1': {'total': 100, 'success': 95, 'rate': 0.95}, ...}

recent = collector.get_recent_feedback(days=7)
# [{'date': '2026-06-05', 'match_rate': 0.91, ...}, ...]
```

---

## 关键指标计算

### 门店匹配率
```
store_match_rate = matched_store_count / store_count
```

### SKU匹配率
```
sku_match_rate = matched_sku_count / sku_count
```

### 层成功率
```
success_rate = (user_confirmed + auto_confirmed) / total_attempts
```

### 用户修改率
```
user_modified_rate = corrections_with_user_change / total_orders
```

---

## 健康度评估

当 `get_health_score()` 被调用时，返回：

```python
{
    "overall": 0.87,              # 综合健康度
    "store_match_rate_avg": 0.92, # 平均门店匹配率
    "sku_match_rate_avg": 0.88,  # 平均SKU匹配率
    "user_modified_rate": 0.23,   # 用户修改率（越低越好）
    "low_match_alert": False,    # 是否触发低匹配率告警
    "recommendations": [
        "SKU匹配率本周下降3%，建议检查新增商品名称规范",
        "layer_3 别名匹配成功率偏低，建议补充别名库"
    ]
}
```

---

*Phase 1 实现文档 | 2026-06-05*