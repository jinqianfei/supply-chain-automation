"""
运营日志记录器 - 记录每次 Skill 处理结果

使用方式：
    from logger import OperationLogger

    logger = OperationLogger(skill_name="skill_order_to_huading_template")
    logger.log_order(
        order_id="ORDER_20260604_001",
        result={
            "matched": True,
            "confidence": 0.95,
            "sku_code": "SK260315000018",
            "user_action": "auto",  # auto/confirm/skip/correct
        },
        meta={
            "store_id": "STORE_001",
            "item_count": 5,
            "processing_time_ms": 1234,
        }
    )
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


class OperationLogger:
    """运营日志记录器"""

    def __init__(
        self,
        skill_name: str,
        log_dir: str = None,
        db_config: dict = None,
    ):
        self.skill_name = skill_name
        self.log_dir = Path(log_dir) if log_dir else Path(__file__).parent.parent / "data"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / f"{skill_name}_log.jsonl"
        self.db_config = db_config

    def log_order(
        self,
        order_id: str,
        result: Dict[str, Any],
        meta: Dict[str, Any],
    ):
        """
        记录单笔订单处理结果

        Args:
            order_id: 订单ID
            result: 处理结果 {
                matched: bool,
                confidence: float,
                sku_code: str,
                user_action: str,  # auto/confirm/skip/correct
                error: str,
            }
            meta: 附加信息 {
                store_id: str,
                item_count: int,
                processing_time_ms: int,
                owner_code: str,
            }
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "skill_name": self.skill_name,
            "order_id": order_id,
            # 处理结果
            "matched": result.get("matched", False),
            "confidence": result.get("confidence", 0.0),
            "sku_code": result.get("sku_code", ""),
            "user_action": result.get("user_action", "auto"),
            "error": result.get("error", ""),
            # 附加信息
            "store_id": meta.get("store_id", ""),
            "owner_code": meta.get("owner_code", ""),
            "item_count": meta.get("item_count", 0),
            "processing_time_ms": meta.get("processing_time_ms", 0),
        }

        self._append(entry)
        return entry

    def log_batch(
        self,
        batch_id: str,
        results: list,
        meta: Dict[str, Any],
    ):
        """
        记录批量处理结果

        Args:
            batch_id: 批次ID
            results: 处理结果列表
            meta: 附加信息
        """
        for i, r in enumerate(results):
            self.log_order(
                order_id=f"{batch_id}_{i+1}",
                result=r,
                meta=meta,
            )

    def _append(self, entry: dict):
        """追加到 JSONL 文件"""
        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _write_db(self, entry: dict):
        """写入数据库（如果配置了）"""
        if not self.db_config:
            return

        try:
            import psycopg2
            conn = psycopg2.connect(**self.db_config)
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO operation_logs (
                    skill_name, order_id, matched, confidence,
                    sku_code, user_action, error, store_id,
                    item_count, processing_time_ms
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """, [
                entry["skill_name"],
                entry["order_id"],
                entry["matched"],
                entry["confidence"],
                entry["sku_code"],
                entry["user_action"],
                entry["error"],
                entry["store_id"],
                entry["item_count"],
                entry["processing_time_ms"],
            ])
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            # 降级：写入文件
            self._append({**entry, "db_error": str(e)})

    def query_stats(
        self,
        start_date: str = None,
        end_date: str = None,
        store_id: str = None,
    ) -> Dict[str, Any]:
        """
        查询统计数据

        Returns:
            {
                total: int,
                matched: int,
                avg_confidence: float,
                low_conf_count: int,
                avg_processing_time: float,
            }
        """
        if not self.log_file.exists():
            return {"total": 0, "matched": 0, "avg_confidence": 0, "low_conf_count": 0}

        stats = {
            "total": 0,
            "matched": 0,
            "low_confidence": 0,
            "confidence_sum": 0,
            "processing_time_sum": 0,
            "actions": {"auto": 0, "confirm": 0, "skip": 0, "correct": 0},
        }

        with open(self.log_file) as f:
            for line in f:
                entry = json.loads(line)
                # 日期过滤
                ts = entry.get("timestamp", "")
                if start_date and ts < start_date:
                    continue
                if end_date and ts > end_date:
                    continue
                # 门店过滤
                if store_id and entry.get("store_id") != store_id:
                    continue

                stats["total"] += 1
                if entry.get("matched"):
                    stats["matched"] += 1
                if entry.get("confidence", 1) < 0.8:
                    stats["low_confidence"] += 1
                stats["confidence_sum"] += entry.get("confidence", 0)
                stats["processing_time_sum"] += entry.get("processing_time_ms", 0)

                action = entry.get("user_action", "auto")
                stats["actions"][action] = stats["actions"].get(action, 0) + 1

        stats["avg_confidence"] = stats["confidence_sum"] / stats["total"] if stats["total"] > 0 else 0
        stats["avg_processing_time"] = stats["processing_time_sum"] / stats["total"] if stats["total"] > 0 else 0

        return stats