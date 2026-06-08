"""
learn/collector.py — FeedbackCollector（v5.9.0 Phase 1）

职责：
1. 订阅 EventBus 上的 10 个事件
2. 将事件数据写入 order_feedback / order_corrections / layer_success_rate 表
3. 维护当前订单的上下文状态
4. 提供查询接口（统计、健康度）

原则：
- 只负责数据写入，不修改 Skill 业务逻辑
- 每个事件写入后，更新 layer_success_rate 统计
- 订单完成时写入 order_feedback 主表
- 数据库连接失败不影响主流程（容错）
"""
import time
from typing import Optional, Dict, Any, List

# 进程内全局单例（避免重复订阅）
_collector_instance: Optional["FeedbackCollector"] = None


def init_feedback_collector(db_config: dict) -> "FeedbackCollector":
    """初始化全局 FeedbackCollector（重复调用返回旧实例）"""
    global _collector_instance
    if _collector_instance is None:
        _collector_instance = FeedbackCollector(db_config)
    return _collector_instance


def get_feedback_collector() -> Optional["FeedbackCollector"]:
    """获取已初始化的 FeedbackCollector（未初始化返回 None）"""
    return _collector_instance


class FeedbackCollector:
    def __init__(self, db_config: dict):
        self.db_config = db_config
        self._current_order: Optional[Dict] = None  # 当前订单上下文
        self._order_started_at: Optional[float] = None

        # 订阅 10 个事件
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
            "session_id": data.get("session_id", ""),
            "store_name_submitted": data.get("store_name_submitted", ""),
            "store_confirm_needed": True,
            "store_candidates": data.get("candidates", []) or [],
            "store_top_similarity": float(data.get("top_similarity", 0) or 0),
            "store_match_layer": data.get("match_layer", ""),
            "sku_items": [],
            "corrections": [],
            "modifications": [],
            "user_modified": False,
            "store_count": 1,
            "started_at": time.time(),
        }
        self._order_started_at = time.time()

    def on_store_confirmed(self, data: Dict):
        """用户确认了门店"""
        if not self._current_order:
            return
        self._current_order["store_confirmed"] = True
        self._current_order["store_selected"] = data.get("selected_store", {}) or {}
        self._current_order["store_match_layer"] = data.get("match_type", "")
        self._current_order["store_top_similarity"] = float(data.get("top_similarity", 1.0) or 1.0)
        self._update_layer_stats(
            entity_type="store",
            layer_name=data.get("match_type", "unknown"),
            match_score=float(data.get("top_similarity", 1.0) or 1.0),
            confirmed=True,
        )

    def on_store_corrected(self, data: Dict):
        """用户纠正了门店"""
        if not self._current_order:
            return
        self._current_order["store_corrected"] = True
        self._current_order["corrections"].append({
            "type": "store",
            "original": data.get("store_name_submitted", ""),
            "original_name": data.get("store_name_submitted", ""),
            "corrected": data.get("user_corrected_to", {}),
            "match_layer": data.get("match_type", ""),
            "match_score": float(data.get("match_score", 0) or 0),
        })
        self._update_layer_stats(
            entity_type="store",
            layer_name=data.get("match_type", "unknown"),
            match_score=float(data.get("match_score", 0) or 0),
            confirmed=False,
        )

    def on_sku_confirm_needed(self, data: Dict):
        """SKU 需要确认"""
        if not self._current_order:
            return
        self._current_order["sku_confirm_needed"] = True
        self._current_order["sku_items"] = data.get("items", []) or []

    def on_sku_confirmed(self, data: Dict):
        """用户确认了 SKU 列表"""
        if not self._current_order:
            return
        self._current_order["sku_confirmed"] = True
        for item in data.get("items", []) or []:
            self._update_layer_stats(
                entity_type="sku",
                layer_name=item.get("match_layer", "unknown"),
                match_score=float(item.get("match_score", 0) or 0),
                confirmed=True,
            )

    def on_sku_corrected(self, data: Dict):
        """用户纠正了 SKU"""
        if not self._current_order:
            return
        self._current_order["sku_corrected"] = True
        for item in data.get("items", []) or []:
            self._current_order["corrections"].append({
                "type": "sku",
                "seq": item.get("seq", 0),
                "original_name": item.get("original_name", ""),
                "corrected": item.get("user_corrected_to", {}),
                "match_layer": item.get("match_layer", ""),
                "match_score": float(item.get("match_score", 0) or 0),
            })
            self._update_layer_stats(
                entity_type="sku",
                layer_name=item.get("match_layer", "unknown"),
                match_score=float(item.get("match_score", 0) or 0),
                confirmed=False,
            )

    def on_user_modified(self, data: Dict):
        """用户修改了字段"""
        if not self._current_order:
            return
        self._current_order["user_modified"] = True
        self._current_order["modifications"].extend(data.get("modifications", []) or [])

    def on_order_complete(self, data: Dict):
        """订单完成：写入主表 + 释放上下文"""
        if not self._current_order:
            self._current_order = {"session_id": data.get("session_id", ""), "started_at": time.time()}

        # 计算处理时长
        processing_time_ms = int(data.get("processing_time_ms", 0) or 0)
        if not processing_time_ms and self._order_started_at:
            processing_time_ms = int((time.time() - self._order_started_at) * 1000)

        order = {
            **self._current_order,
            **data,
            "processing_time_ms": processing_time_ms,
            "completed_at": time.time(),
        }
        self._write_order_feedback(order)
        # 写入结构化 corrections
        feedback_id = self._last_feedback_id
        if feedback_id and order.get("corrections"):
            self._write_corrections(feedback_id, order["corrections"])
        self._current_order = None
        self._order_started_at = None

    def on_order_cancelled(self, data: Dict):
        """订单取消"""
        self._current_order = None
        self._order_started_at = None

    def on_alert_raised(self, data: Dict):
        """系统告警（暂只打日志，可扩展）"""
        print(f"[FeedbackCollector Alert] {data.get('severity', '?')} — {data.get('message', '')}")

    # ── 数据库写入 ─────────────────────────────────

    _last_feedback_id: Optional[int] = None  # 最近一次写入的 feedback_id

    def _get_conn(self):
        """获取数据库连接（懒加载 + 容错）"""
        try:
            import psycopg2
            return psycopg2.connect(**self.db_config)
        except Exception as e:
            print(f"[FeedbackCollector] DB connect error: {e}", flush=True)
            return None

    def _write_order_feedback(self, order: Dict) -> Optional[int]:
        """写入 order_feedback 主表，返回 feedback_id"""
        from .adapter import EventAdapter
        record = EventAdapter.to_order_feedback(order, order)

        conn = self._get_conn()
        if not conn:
            return None
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO order_feedback (
                    session_id, order_type,
                    store_count, sku_count,
                    matched_store_count, matched_sku_count,
                    store_match_rate, sku_match_rate,
                    user_confirmed, user_modified,
                    corrections, modifications,
                    processing_time_ms, skill_version,
                    owner_code, source_file, alerts,
                    data_source
                ) VALUES (
                    %(session_id)s, %(order_type)s,
                    %(store_count)s, %(sku_count)s,
                    %(matched_store_count)s, %(matched_sku_count)s,
                    %(store_match_rate)s, %(sku_match_rate)s,
                    %(user_confirmed)s, %(user_modified)s,
                    %(corrections)s::jsonb, %(modifications)s::jsonb,
                    %(processing_time_ms)s, %(skill_version)s,
                    %(owner_code)s, %(source_file)s, %(alerts)s::jsonb,
                    %(data_source)s
                )
                RETURNING id
            """, record)
            feedback_id = cur.fetchone()[0]
            conn.commit()
            cur.close()
            self._last_feedback_id = feedback_id
            return feedback_id
        except Exception as e:
            print(f"[FeedbackCollector] write order_feedback error: {e}", flush=True)
            conn.rollback()
            return None
        finally:
            conn.close()

    def _write_corrections(self, feedback_id: int, corrections: List[Dict]):
        """写入 order_corrections 表（结构化纠正）"""
        from .adapter import EventAdapter
        records = EventAdapter.to_corrections(feedback_id, corrections)
        if not records:
            return

        conn = self._get_conn()
        if not conn:
            return
        try:
            cur = conn.cursor()
            for r in records:
                cur.execute("""
                    INSERT INTO order_corrections (
                        feedback_id, correction_type, entity_name,
                        original_value, corrected_value,
                        match_layer, match_score, auto_matched
                    ) VALUES (
                        %(feedback_id)s, %(correction_type)s, %(entity_name)s,
                        %(original_value)s, %(corrected_value)s,
                        %(match_layer)s, %(match_score)s, %(auto_matched)s
                    )
                """, r)
            conn.commit()
            cur.close()
        except Exception as e:
            print(f"[FeedbackCollector] write order_corrections error: {e}", flush=True)
            conn.rollback()
        finally:
            conn.close()

    def _update_layer_stats(self, entity_type: str, layer_name: str,
                            match_score: float, confirmed: bool):
        """更新匹配层成功率统计"""
        conn = self._get_conn()
        if not conn:
            return
        try:
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
        except Exception as e:
            print(f"[FeedbackCollector] update layer_success_rate error: {e}", flush=True)
            conn.rollback()
        finally:
            conn.close()

    # ── 查询接口（可选） ─────────────────────────

    def get_layer_stats(self, entity_type: str) -> Dict:
        """查询某类实体的各层成功率"""
        conn = self._get_conn()
        if not conn:
            return {}
        try:
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
            return {r[0]: {
                "description": r[1],
                "total": r[2], "success": r[3],
                "corrected": r[4], "rate": r[6], "avg_score": r[7]
            } for r in rows}
        except Exception as e:
            print(f"[FeedbackCollector] get_layer_stats error: {e}", flush=True)
            return {}
        finally:
            conn.close()

    def get_recent_feedback(self, days: int = 7) -> List[Dict]:
        """查询最近 N 天的订单反馈"""
        conn = self._get_conn()
        if not conn:
            return []
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT order_date, total_orders, avg_store_match_rate,
                       avg_sku_match_rate, avg_processing_time_ms,
                       confirm_rate, modify_rate, avg_corrections
                FROM v_daily_feedback_stats
                WHERE order_date >= CURRENT_DATE - %s
                ORDER BY order_date DESC
            """, (days,))
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            cur.close()
            return rows
        except Exception as e:
            print(f"[FeedbackCollector] get_recent_feedback error: {e}", flush=True)
            return []
        finally:
            conn.close()
