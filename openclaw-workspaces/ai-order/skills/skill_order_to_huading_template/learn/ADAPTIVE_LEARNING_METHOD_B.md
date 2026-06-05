# AI建单助手自适应学习系统 — 方案 B（事件驱动）

> **版本：** v1.0
> **日期：** 2026-06-05
> **方案：** 事件总线 + 适配器，完全解耦 Skill业务逻辑

---

## 1. 核心设计原则

| 原则 | 说明 |
|------|------|
| **零侵入业务逻辑** | Skill 的 `tools/`、`db/`、`field_mapping/` 全部不改 |
| **事件驱动** | Skill 只在确认点发出事件，不关心谁来处理 |
| **单向解耦** | 事件只能从 Skill 发出，FeedbackCollector 订阅，不反向调用 Skill |
| **可独立测试** | FeedbackCollector 可以不启动 Skill 单独运行 |
| **数据可追溯** | 每个事件带 session_id + timestamp，可追溯到原始会话 |

---

## 2. 架构图

```
┌──────────────────────────────────────────────────────────────────┐
│ skill_order_to_huading_template (__init__.py)         │
│                                                                   │
│  parse() ──→ match_store() ──→ match_sku() ──→ generate()        │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ EventBus.emit() × 4 处（仅在「需要用户确认」的节点发出）    │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────┼──────────────────────────────────┘
                               │ EventBus 单向发出
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  events/                                                          │
│  bus.py — 极简事件总线（12行，无外部依赖）                          │
│                                                                   │
│  class EventBus:                                                 │
│      _handlers = {} ← 进程内订阅表 │
│      on(event, handler) → 订阅                                    │
│      emit(event, data)  → 发出（同步调用所有handler）              │
│      off(event, h)      → 取消订阅 │
└──────────────────────────────┬──────────────────────────────────┘
                               │ 订阅者调用
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  learn/                                   │
│ │
│  collector.py    — 订阅事件，写入数据库     │
│  adapter.py      — 事件数据→DB记录转换     │
│  schema.sql      — 建表SQL │
│  pattern_memory.py — 别名自动学习(Phase2) │
│  health_score.py  — 健康度评估(Phase3) │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. 事件总线（events/bus.py）

### 实现代码

```python
"""
events/bus.py — 极简事件总线

原则：
- 单例模式（进程内唯一）
- 同步调用（顺序执行，不并发）
- 容错（handler报错不影响主流程）
- 无外部依赖（纯标准库）
"""
from typing import Callable, Dict, List, Any


class EventBus:
    """
    进程内事件总线。
    Skill 发出事件 → FeedbackCollector 接收并写入数据库。

    用法：
        # 订阅
        EventBus.on("store_confirmed", my_handler)

        # 发出
        EventBus.emit("store_confirmed", {"store_name": "制茶青年", ...})
    """
    _handlers: Dict[str, List[Callable]] = {}

    @classmethod
    def on(cls, event: str, handler: Callable[[Dict], None]) -> None:
        """订阅事件。同一事件可订阅多个 handler。"""
        if event not in cls._handlers:
            cls._handlers[event] = []
        cls._handlers[event].append(handler)

    @classmethod
    def off(cls, event: str, handler: Callable[[Dict], None]) -> None:
        """取消订阅。"""
        if event in cls._handlers:
            cls._handlers[event] = [h for h in cls._handlers[event] if h != handler]

    @classmethod
    def emit(cls, event: str, data: Dict[str, Any]) -> None:
        """发出事件，同步调用所有 handler，任一 handler 异常不影响其他。"""
        for handler in cls._handlers.get(event, []):
            try:
                handler(data)
            except Exception as e:
                print(f"[EventBus] handler error in '{event}': {e}", flush=True)

    @classmethod
    def clear(cls) -> None:
        """清除所有订阅（主要用于测试）。"""
        cls._handlers.clear()
```

### 设计说明

| 特性 | 说明 |
|------|------|
| 同步调用 | `emit()` 立即执行所有 handler，不异步 |
| 容错 | handler 报错只打印日志，不阻断 Skill 主流程 |
| 单例 | 进程内唯一，所有模块共享 |
| 无状态 | EventBus 只负责路由，不存储数据 |
| 无外部依赖 | 纯 Python 标准库，可移植任意项目 |

---

## 4. 事件定义

### 4.1 事件清单

| 事件名 | 触发时机 | 方向 | 说明 |
|--------|---------|------|------|
| `store_confirm_needed` | 系统返回需要用户确认门店 | Skill→Collector | 用户尚未响应 |
| `store_confirmed` | 用户确认/接受了建议的门店 | Skill→Collector | 用户同意了 |
| `store_corrected` | 用户纠正了门店选择 | Skill→Collector | 用户改了 |
| `sku_confirm_needed` | 系统返回需要用户确认 SKU | Skill→Collector | 用户尚未响应 |
| `sku_confirmed` | 用户确认/接受了建议的 SKU | Skill→Collector | 用户同意了 |
| `sku_corrected` | 用户纠正了某个 SKU | Skill→Collector | 用户改了 |
| `order_complete` | 模板生成完成 | Skill→Collector | 订单完成 |
| `order_cancelled` | 用户取消订单 | Skill→Collector | 订单取消 |
| `user_modified` | 用户在确认模板时修改了字段 | Skill→Collector | 修改了字段 |
| `alert_raised` | 系统产生告警 | Skill→Collector | 异常告警 |

### 4.2 事件 Payload 详细定义

#### `store_confirm_needed`

```python
{
    "event": "store_confirm_needed",
    "session_id": str,              # OpenClaw session ID
    "timestamp": float,              # Unix timestamp（秒）
    "store_name_submitted": str,   # 用户输入的门店名
    "matched_store": {
        "store_code": str,
        "store_name": str,
        "owner_code": str,
        "owner_name": str,
        "warehouse_code": str,
        "warehouse_name": str,
    },
    "candidates": [
        {
            "store_code": str,
            "store_name": str,
            "similarity": float,   # 0.0~1.0
            "match_type": str,      # "prefix"/"fuzzy"/"alias"...
            "match_method": str,    # "layer_2" 等
        }
    ],
    "top_similarity": float,        # 顶候选相似度
    "match_type": str,              # "layer_2" 等
    "match_layer": str,              # 同 match_type（冗余，方便查询）
    "need_customer_hint": bool,     # 是否需要用户提供线索
}
```

#### `store_confirmed`

```python
{
    "event": "store_confirmed",
    "session_id": str,
    "timestamp": float,
    "store_name_submitted": str, # 用户输入的原始名称
    "selected_store": {
        "store_code": str,
        "store_name": str,
        "owner_code": str,
    },
    "from_candidates": bool,        # 用户是否从候选列表选择
    "top_similarity": float,         # 原始匹配分数
    "match_type": str,               # "layer_2"
    "user_response_text": str,      # 用户原始回复文本
}
```

#### `store_corrected`

```python
{
    "event": "store_corrected",
    "session_id": str,
    "timestamp": float,
    "store_name_submitted": str,   # 用户输入的原始名称
    "system_suggested": {           # 系统建议的
        "store_code": str,
        "store_name": str,
    },
    "user_corrected_to": {          # 用户纠正后的
        "store_code": str,
        "store_name": str,
    },
    "match_type": str, # 系统匹配时用的层
    "match_score": float,            # 系统匹配分数
    "user_response_text": str,
}
```

#### `sku_confirm_needed`

```python
{
    "event": "sku_confirm_needed",
    "session_id": str,
    "timestamp": float,
    "store_code": str, # 所属门店
    "items": [
        {
            "seq": int,
            "original_name": str,   # 订单原始商品名
            "matched_sku": {
                "sku_code": str,
                "sku_name": str,
                "unit_type": str,
                "huading_quantity": int,
                "huading_unit": str,
            },
            "match_score": float,
            "match_layer": str,      # "layer_3"
            "match_layer_description": str,
        }
    ],
    "total_sku_count": int,
    "confirmed_count": int,          # 自动确认数
    "need_confirm_count": int,        # 需要确认数
    "match_rate": float,
}
```

#### `sku_confirmed`

```python
{
    "event": "sku_confirmed",
    "session_id": str,
    "timestamp": float,
    "store_code": str,
    "items": [
        {
            "seq": int,
            "original_name": str,
            "confirmed_sku": {"sku_code": str, "sku_name": str},
            "match_score": float,
            "match_layer": str,
        }
    ],
    "confirmed_count": int,
}
```

#### `sku_corrected`

```python
{
    "event": "sku_corrected",
    "session_id": str,
    "timestamp": float,
    "store_code": str,
    "items": [
        {
            "seq": int,
            "original_name": str,
            "system_suggested": {"sku_code": str, "sku_name": str},
            "user_corrected_to": {"sku_code": str, "sku_name": str},
            "modified_field": str,   # "sku_code"/"sku_name"/"unit_type"
            "match_score": float,
            "match_layer": str,
            "user_response_text": str,
        }
    ],
    "corrected_count": int,
}
```

#### `order_complete`

```python
{
    "event": "order_complete",
    "session_id": str,
    "timestamp": float,
    "order_type": str,              # "excel"/"image"/"pdf"/"word"/"text"
    "store": {
        "store_code": str,
        "store_name": str,
        "owner_code": str,
    },
    "sku_summary": {
        "total": int,
        "auto_matched": int,
        "user_confirmed": int,
        "user_corrected": int,
        "unmatched": int,
    },
    "match_rates": {
        "store_match_rate": float,
        "sku_match_rate": float,
    },
    "user_modified": bool,
    "user_confirmed": bool,
    "processing_time_ms": int,
    "skill_version": str,           # "5.8.0"
    "owner_code": str,
    "source_file": str,
    "output_file": str,
}
```

#### `user_modified`

```python
{
    "event": "user_modified",
    "session_id": str,
    "timestamp": float,
    "modifications": [
        {
            "seq": int,
            "field": str,           # "sku_code"/"huading_unit"/"unit_type"/"quantity"
            "old_value": str,
            "new_value": str,
        }
    ],
    "modification_count": int,
    "user_response_text": str,
}
```

#### `alert_raised`

```python
{
    "event": "alert_raised",
    "session_id": str,
    "timestamp": float,
    "alert_type": str,              # "low_match_rate"/"timeout"/"unmatched_items"
    "severity": str,                 # "low"/"medium"/"high"/"critical"
    "message": str,
    "detail": dict,
}
```

---

## 5. Skill 改动位置（仅 4 处）

### 改动原则

- **只在 `__init__.py` 的确认点加 1 行 `EventBus.emit()`**
- **不修改任何业务逻辑**，只发出事件
- **每个事件在 `emit` 之前的数据已经准备好**

### 改动位置详情

#### 改动点 A：门店需要确认时（~line 1765）

**现有代码：**
```python
if si.get("need_confirm") or si.get("candidates"):
    top_c = si["candidates"][0] if si.get("candidates") else {}
    top_sim = top_c.get("similarity", 0)
    return {"need_store_confirm": True, ...}
```

**加 1 行：**
```python
if si.get("need_confirm") or si.get("candidates"):
    top_c = si["candidates"][0] if si.get("candidates") else {}
    top_sim = top_c.get("similarity", 0)

    EventBus.emit("store_confirm_needed", { # ← 加这一行
        "session_id": self.session_id,
        "timestamp": time.time(),
        "store_name_submitted": store_name_for_match,
        "matched_store": {"store_code": si.get("store_code", ""), "store_name": si.get("store_name", "")},
        "candidates": si.get("candidates", []),
        "top_similarity": top_sim,
        "match_type": si.get("match_type", ""),
        "match_layer": si.get("match_type", ""),
        "need_customer_hint": si.get("need_customer_hint", False),
    })

    return {"need_store_confirm": True, ...}
```

#### 改动点 B：用户确认门店时（~line 1743）

**现有代码：**
```python
if confirmed_store:
    si = confirmed_store
```

**加 1 行：**
```python
if confirmed_store:
    si = confirmed_store
    EventBus.emit("store_confirmed", {              # ← 加这一行
        "session_id": self.session_id,
        "timestamp": time.time(),
        "store_name_submitted": store_name_for_match,
        "selected_store": si,
        "from_candidates": True,
        "top_similarity": si.get("similarity", 1.0),
        "match_type": si.get("match_type", ""),
        "user_response_text": "user_selected_from_candidates",
    })
```

#### 改动点 C：订单完成时（`process()` 结束时）

**现有代码：**
```python
return {"success": True, "file_path": output_path, ...}
```

**加 1 行：**
```python
EventBus.emit("order_complete", {                  # ← 加这一行
    "session_id": self.session_id,
    "timestamp": time.time(),
    "order_type": order_type,
    "store": store_info,
    "sku_summary": {...},
    "match_rates": {"store_match_rate": ..., "sku_match_rate": ...},
    "user_modified": any_modification,
    "user_confirmed": not any_modification,
    "processing_time_ms": elapsed_ms,
    "skill_version": self.__class__.__version__,
    "owner_code": owner_code,
    "source_file": order_input if isinstance(order_input, str) else "",
    "output_file": output_path,
})

return {"success": True, "file_path": output_path, ...}
```

#### 改动点 D：用户修改字段时（`parse_user_feedback()` 识别到 modifications 时）

**现有代码：**
```python
if modifications:
    return {"action": "modify", "modifications": modifications, ...}
```

**加 1 行：**
```python
if modifications:
    EventBus.emit("user_modified", { # ← 加这一行
        "session_id": self.session_id,
        "timestamp": time.time(),
        "modifications": modifications,
        "modification_count": len(modifications),
        "user_response_text": user_message,
    })

    return {"action": "modify", "modifications": modifications, ...}
```

### 改动汇总

| 位置 | 行数 | 事件 | 数据来源 |
|------|------|------|---------|
| `__init__.py` ~1765 | 1行 | `store_confirm_needed` | `si` 字典已有 |
| `__init__.py` ~1743 | 1行 | `store_confirmed` | `confirmed_store` 已有 |
| `__init__.py` `process()` 结束 | 1行 | `order_complete` | 本地变量已有 |
| `__init__.py` `parse_user_feedback()` | 1行 | `user_modified` | `modifications` 已有 |

**总改动量：4 行代码。**

---

## 6. learn/ 模块设计

### 6.1 目录结构

```
learn/
├── __init__.py
├── collector.py         # FeedbackCollector（主类）
├── adapter.py          # 事件 Payload → DB Record 转换
├── schema.sql          # 建表 SQL
├── pattern_memory.py # 别名自动学习（Phase 2）
├── health_score.py     # 健康度评估（Phase 3）
└── README.md
```

### 6.2 collector.py

```python
"""
learn/collector.py — FeedbackCollector

职责：
1. 订阅 EventBus 上的所有事件
2. 将事件数据写入数据库
3. 维护当前订单的上下文状态
4. 提供查询接口（统计、健康度）

原则：
- 只负责数据写入，不修改 Skill 业务逻辑
- 每个事件写入后，更新 layer_success_rate 统计
- 订单完成时写入 order_feedback 主表
"""
from typing import Optional, Dict, Any, List
import time


class FeedbackCollector:
    def __init__(self, db_config: dict):
        self.db_config = db_config
        self._current_order: Optional[Dict] = None  # 当前订单上下文

        from events.bus import EventBus
        EventBus.on("store_confirm_needed", self.on_store_confirm_needed)
        EventBus.on("store_confirmed", self.on_store_confirmed)
        EventBus.on("store_corrected", self.on_store_corrected)
        EventBus.on("sku_confirm_needed", self.on_sku_confirm_needed)
        EventBus.on("sku_confirmed", self.on_sku_confirmed)
        EventBus.on("sku_corrected", self.on_sku_corrected)
        EventBus.on("order_complete", self.on_order_complete)
        EventBus.on("order_cancelled", self.on_order_cancelled)
        EventBus.on("user_modified", self.on_user_modified)
        EventBus.on("alert_raised", self.on_alert_raised)

    # ── 事件处理 ───────────────────────────────────

    def on_store_confirm_needed(self, data: Dict):
        """门店需要确认：初始化订单上下文"""
        self._current_order = {
            "session_id": data["session_id"],
            "store_name_submitted": data["store_name_submitted"],
            "store_confirm_needed": True,
            "store_candidates": data.get("candidates", []),
            "store_top_similarity": data.get("top_similarity", 0),
            "store_match_layer": data.get("match_layer", ""),
            "sku_items": [],
            "corrections": [],
            "modifications": [],
            "user_modified": False,
            "started_at": time.time(),
        }

    def on_store_confirmed(self, data: Dict):
        """用户确认了门店"""
        if not self._current_order:
            return
        self._current_order["store_confirmed"] = True
        self._current_order["store_selected"] = data["selected_store"]
        self._current_order["store_match_layer"] = data.get("match_type", "")
        self._current_order["store_top_similarity"] = data.get("top_similarity", 1.0)
        self._update_layer_stats(
            entity_type="store",
            layer_name=data.get("match_type", "unknown"),
            match_score=data.get("top_similarity", 1.0),
            confirmed=True,
        )

    def on_store_corrected(self, data: Dict):
        """用户纠正了门店"""
        if not self._current_order:
            return
        self._current_order["store_corrected"] = True
        self._current_order["corrections"].append({
            "type": "store",
            "original": data["store_name_submitted"],
            **data["user_corrected_to"],
            "match_layer": data.get("match_type", ""),
            "match_score": data.get("match_score", 0),
        })
        self._update_layer_stats(
            entity_type="store",
            layer_name=data.get("match_type", "unknown"),
            match_score=data.get("match_score", 0),
            confirmed=False,
        )

    def on_sku_confirm_needed(self, data: Dict):
        """SKU 需要确认"""
        if not self._current_order:
            return
        self._current_order["sku_confirm_needed"] = True
        self._current_order["sku_items"] = data.get("items", [])

    def on_sku_confirmed(self, data: Dict):
        """用户确认了 SKU 列表"""
        if not self._current_order:
            return
        self._current_order["sku_confirmed"] = True
        for item in data.get("items", []):
            self._update_layer_stats(
                entity_type="sku",
                layer_name=item.get("match_layer", "unknown"),
                match_score=item.get("match_score", 0),
                confirmed=True,
            )

    def on_sku_corrected(self, data: Dict):
        """用户纠正了 SKU"""
        if not self._current_order:
            return
        self._current_order["sku_corrected"] = True
        for item in data.get("items", []):
            self._current_order["corrections"].append({
                "type": "sku",
                "seq": item["seq"],
                "original_name": item["original_name"],
                "corrected": item["user_corrected_to"],
                "match_layer": item.get("match_layer", ""),
                "match_score": item.get("match_score", 0),
            })
            self._update_layer_stats(
                entity_type="sku",
                layer_name=item.get("match_layer", "unknown"),
                match_score=item.get("match_score", 0),
                confirmed=False,
            )

    def on_user_modified(self, data: Dict):
        """用户修改了字段"""
        if not self._current_order:
            return
        self._current_order["user_modified"] = True
        self._current_order["modifications"].extend(data.get("modifications", []))

    def on_order_complete(self, data: Dict):
        """订单完成：写入主表 + 释放上下文"""
        if not self._current_order:
            self._current_order = {"session_id": data.get("session_id", "")}

        order = {**self._current_order, **data, "completed_at": time.time()}
        self._write_order_feedback(order)
        self._current_order = None

    def on_order_cancelled(self, data: Dict):
        """订单取消"""
        self._current_order = None

    def on_alert_raised(self, data: Dict):
        """系统告警"""
        self._write_alert(data)

    # ── 数据库写入 ─────────────────────────────────

    def _write_order_feedback(self, order: Dict):
        """写入 order_feedback 主表"""
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(**self.db_config)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO order_feedback (
                session_id, order_date, order_type,
                store_count, sku_count,
                matched_store_count, matched_sku_count,
                store_match_rate, sku_match_rate,
                user_confirmed, user_modified,
                corrections, modifications,
                processing_time_ms, skill_version,
                owner_code, source_file, alerts,
                data_source
            ) VALUES (
                %(session_id)s, CURRENT_DATE, %(order_type)s,
                %(store_count)s, %(sku_count)s,
                %(matched_store_count)s, %(matched_sku_count)s,
                %(store_match_rate)s, %(sku_match_rate)s,
                %(user_confirmed)s, %(user_modified)s,
                %(corrections)s, %(modifications)s,
                %(processing_time_ms)s, %(skill_version)s,
                %(owner_code)s, %(source_file)s, %(alerts)s,
                'event_bus'
            )
        """, {
            "session_id": order.get("session_id"),
            "order_type": order.get("order_type", "unknown"),
            "store_count": 1,
            "sku_count": order.get("sku_summary", {}).get("total", 0),
            "matched_store_count": 1 if order.get("store_confirmed") else 0,
            "matched_sku_count": order.get("sku_summary", {}).get("auto_matched", 0),
            "store_match_rate": order.get("store_top_similarity", 0),
            "sku_match_rate": order.get("match_rates", {}).get("sku_match_rate", 0),
            "user_confirmed": order.get("user_confirmed", False),
            "user_modified": order.get("user_modified", False),
            "corrections": psycopg2.extras.Jsonb(order.get("corrections", [])),
            "modifications": psycopg2.extras.Jsonb(order.get("modifications", [])),
            "processing_time_ms": order.get("processing_time_ms", 0),
            "skill_version": order.get("skill_version", ""),
            "owner_code": order.get("owner_code", ""),
            "source_file": order.get("source_file", ""),
            "alerts": psycopg2.extras.Jsonb(order.get("alerts", [])),
        })
        conn.commit()
        cur.close()
        conn.close()

    def _write_alert(self, data: Dict):
        """写入告警记录（可扩展）"""
        print(f"[Alert] {data.get('severity')} — {data.get('message')}")

    def _update_layer_stats(self, entity_type: str, layer_name: str,
                          match_score: float, confirmed: bool):
        """更新匹配层成功率统计"""
        import psycopg2
        conn = psycopg2.connect(**self.db_config)
        cur = conn.cursor()
        if confirmed:
            cur.execute("""
                UPDATE layer_success_rate
                SET total_attempts = total_attempts + 1,
                    success_count = success_count + 1,
                    auto_success_count = auto_success_count + 1,
                    success_rate = (success_count + 1.0) / (total_attempts + 1),
                    avg_match_score = (avg_match_score * total_attempts + %(score)s) / (total_attempts + 1),
                    updated_at = NOW()
                WHERE entity_type = %(entity)s AND layer_name = %(layer)s
            """, {"score": match_score, "entity": entity_type, "layer": layer_name})
        else:
            cur.execute("""
                UPDATE layer_success_rate
                SET total_attempts = total_attempts + 1,
                    user_corrected_count = user_corrected_count + 1,
                    success_rate = success_count::FLOAT / (total_attempts + 1),
                    avg_match_score = (avg_match_score * total_attempts + %(score)s) / (total_attempts + 1),
                    updated_at = NOW()
                WHERE entity_type = %(entity)s AND layer_name = %(layer)s
            """, {"score": match_score, "entity": entity_type, "layer": layer_name})
        conn.commit()
        cur.close()
        conn.close()

    # ── 查询接口 ─────────────────────────────────

    def get_layer_stats(self, entity_type: str) -> Dict:
        """查询某类实体的各层成功率"""
        import psycopg2
        conn = psycopg2.connect(**self.db_config)
        cur = conn.cursor()
        cur.execute("""
            SELECT layer_name, layer_description,
                   total_attempts, success_count, user_corrected_count,
                   success_rate, avg_match_score
            FROM layer_success_rate
            WHERE entity_type = %s
            ORDER BY layer_name
        """, (entity_type,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return {r[0]: {
            "total": r[2], "success": r[3],
            "corrected": r[4], "rate": r[6], "avg_score": r[7]
        } for r in rows}

    def get_recent_stats(self, days: int = 7) -> List[Dict]:
        """查询最近 N 天的统计"""
        import psycopg2
        conn = psycopg2.connect(**self.db_config)
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM v_daily_feedback_stats WHERE order_date >= CURRENT_DATE - %s",
            (days,)
        )
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return rows
```

### 6.3 adapter.py

```python
"""
learn/adapter.py — 事件适配器

职责：
将 EventBus 发出的原始事件 payload，转换成符合数据库 schema 的记录格式。
做数据清洗、字段映射、默认值填充。

原则：
- 输入是 EventBus 的原始 payload dict
- 输出是符合 schema.sql 表结构的 dict
- 不做数据写入（写入由 collector.py 的 _write 方法执行）
"""
import json
from typing import Dict, Any


class EventAdapter:
    """将事件数据适配为数据库记录格式"""

    @staticmethod
    def to_order_feedback(event_data: Dict, context: Dict) -> Dict:
        """
        合并当前上下文 + order_complete 事件数据
        → order_feedback 表记录
        """
        return {
            "session_id": event_data.get("session_id") or context.get("session_id", ""),
            "order_type": event_data.get("order_type", "unknown"),
            "store_count": 1,
            "sku_count": event_data.get("sku_summary", {}).get("total", 0),
            "matched_store_count": 1 if context.get("store_confirmed") else 0,
            "matched_sku_count": event_data.get("sku_summary", {}).get("auto_matched", 0),
            "store_match_rate": context.get("store_top_similarity", 0),
            "sku_match_rate": event_data.get("match_rates", {}).get("sku_match_rate", 0),
            "user_confirmed": event_data.get("user_confirmed", False),
            "user_modified": event_data.get("user_modified", False),
            "corrections": json.dumps(context.get("corrections", []), ensure_ascii=False),
            "modifications": json.dumps(event_data.get("modifications", []), ensure_ascii=False),
            "processing_time_ms": event_data.get("processing_time_ms", 0),
            "skill_version": event_data.get("skill_version", ""),
            "owner_code": event_data.get("owner_code", ""),
            "source_file": event_data.get("source_file", ""),
            "alerts": json.dumps(event_data.get("alerts", []), ensure_ascii=False),
            "data_source": "event_bus",
        }

    @staticmethod
    def to_corrections(feedback_id: int, corrections: list) -> list:
        """
        将 corrections 列表 → order_corrections 表记录列表
        """
        records = []
        for c in corrections:
            records.append({
                "feedback_id": feedback_id,
                "correction_type": c.get("type", "unknown"),
                "entity_name": c.get("original_name", c.get("original", "")),
                "original_value": str(c.get("original", "")),
                "corrected_value": str(c.get("corrected", "")),
                "match_layer": c.get("match_layer", ""),
                "match_score": c.get("match_score", 0),
                "auto_matched": True,
            })
        return records
```

---

## 7. 初始化流程（Skill 启动时）

```python
# skill_order_to_huading_template/__init__.py 顶部
import sys, os
sys.path.insert(0, os.path.dirname(__file__))  # 让 events/ 可导入

def _init_feedback_collector():
    from learn.collector import FeedbackCollector
    from db.connection import get_connection  # Skill 自带
    # FeedbackCollector 需要 db_config dict
    # Skill自身有 self.db_config，直接复用
    return FeedbackCollector({"host": "localhost", "port": 5432,
                               "database": "neo", "user": "jinqianfei", "password": ""})

# Skill 实例化时自动初始化（加在 __init__ 顶部）
_feedback_collector = _init_feedback_collector()
```

---

## 8. 数据库 Schema

详见 `learn/schema.sql`

**核心表：**
- `order_feedback` — 订单处理反馈主表
- `order_corrections` — 用户纠正记录
- `layer_success_rate` — 匹配层成功率统计
- `v_daily_feedback_stats` — 每日统计视图
- `v_layer_success_rate` — 层成功率视图

**初始化层统计基础数据（11条记录）：**
-门店 6 层：layer_1~layer_6
- SKU 5 层：layer_1~layer_5

---

## 9. 实施计划

| Phase | 任务 | Skill 改动 | 产出 |
|-------|------|-----------|------|
| **B-1** | 搭建 events/bus.py + learn/ 目录 | 0 | 事件总线 + 框架 |
| **B-2** | 实现 collector.py（10个事件订阅 + DB写入） | 0 | 可运行 |
| **B-3** | Skill 的 4 处改动（各加 1 行） | **4 行** | 数据采集 |
| **B-4** | 运行 `schema.sql` 建表 | 0 | 数据库就绪 |
| **B-5** | 单元测试（用 mock 数据验证写入） | 0 | 可测试 |

**与 Phase 1（方案 A）的融合：**
- Phase 1 的 `adaptive_order_learn` Skill 采集粗粒度数据（source='session_parser'）
- Phase B 的事件驱动采集精确数据（source='event_bus'）
- 查询时按 source区分质量，数据合并使用

---

## 10. 与 Phase 1 的关系

| 维度 | Phase 1（方案 A） | Phase B（方案 B） |
|------|------------------|-----------------|
| 触发方式 | HEARTBEAT 定时扫描 sessions | 实时事件 |
| 数据精度 | 从消息文本推断（近似值） | 直接从 Skill 回调获取（精确值） |
| processing_time |不可用 | 精确值 |
| match_score | 正则提取（不精确） | float精确值 |
| source字段 | `session_parser` | `event_bus` |
| Skill 改动 | **零改动** | **4 行** |

两者共用同一套 schema.sql，查询时可 UNION合并。

---

*方案 B 设计文档 | 2026-06-05*