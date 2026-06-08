"""
learn/adapter.py — 事件适配器

职责：将 EventBus 发出的原始事件 payload，转换成符合数据库 schema 的记录格式。
做数据清洗、字段映射、默认值填充。

原则：
- 输入是 EventBus 的原始 payload dict
- 输出是符合 schema.sql 表结构的 dict
- 不做数据写入（写入由 collector.py 的 _write 方法执行）
"""
import json
from typing import Dict, Any, List


class EventAdapter:
    """将事件数据适配为数据库记录格式"""

    @staticmethod
    def to_order_feedback(event_data: Dict, context: Dict) -> Dict:
        """
        合并当前上下文 + order_complete 事件数据
        → order_feedback 表记录
        """
        sku_summary = event_data.get("sku_summary", {}) or {}
        match_rates = event_data.get("match_rates", {}) or {}
        return {
            "session_id": event_data.get("session_id") or context.get("session_id", ""),
            "order_type": event_data.get("order_type", "unknown"),
            "store_count": int(context.get("store_count", 1) or 1),
            "sku_count": int(sku_summary.get("total", 0) or 0),
            "matched_store_count": int(1 if context.get("store_confirmed") else 0),
            "matched_sku_count": int(sku_summary.get("auto_matched", 0) or 0),
            "store_match_rate": float(context.get("store_top_similarity", 0) or 0),
            "sku_match_rate": float(match_rates.get("sku_match_rate", 0) or 0),
            "user_confirmed": bool(event_data.get("user_confirmed", False)),
            "user_modified": bool(event_data.get("user_modified", False)),
            "corrections": json.dumps(context.get("corrections", []), ensure_ascii=False),
            "modifications": json.dumps(event_data.get("modifications", []) or context.get("modifications", []), ensure_ascii=False),
            "processing_time_ms": int(event_data.get("processing_time_ms", 0) or 0),
            "skill_version": event_data.get("skill_version", ""),
            "owner_code": event_data.get("owner_code", ""),
            "source_file": event_data.get("source_file", ""),
            "alerts": json.dumps(event_data.get("alerts", []) or [], ensure_ascii=False),
            "data_source": "event_bus",
        }

    @staticmethod
    def to_corrections(feedback_id: int, corrections: list) -> List[Dict]:
        """
        将 corrections 列表 → order_corrections 表记录列表
        """
        records = []
        for c in corrections or []:
            records.append({
                "feedback_id": feedback_id,
                "correction_type": c.get("type", "unknown"),
                "entity_name": c.get("original_name", c.get("original", "")),
                "original_value": str(c.get("original", "")),
                "corrected_value": str(c.get("corrected", "")),
                "match_layer": c.get("match_layer", ""),
                "match_score": float(c.get("match_score", 0) or 0),
                "auto_matched": bool(c.get("auto_matched", True)),
            })
        return records
