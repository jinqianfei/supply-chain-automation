"""
core/sku_matcher.py — SKU 映射核心模块

职责：
1. 调用 tools/_sku_mapper.py 的 map_sku_batch 进行批量 SKU 匹配
2. 获取 SKU 单位信息（大/中/小单位推断）
3. 格式化匹配结果（与旧接口兼容）
4. 生成映射对照表（单门店 + 多门店汇总）

提取来源：
- __init__.py: _match_sku, _get_sku_unit_info, _get_unit_type,
  _generate_mapping_comparison, _generate_mapping_comparison_multi,
  _clean_product_name
"""
import importlib
from typing import Dict, Any, Optional, List, Tuple


# ---------------------------------------------------------------------------
# 动态导入
# ---------------------------------------------------------------------------

def _import_skill_attr(module_path: str, attr_name: str):
    """Import from installed skill package, with direct-directory fallback."""
    absolute_name = f"skills.skill_order_to_huading_template.{module_path}"
    try:
        module = importlib.import_module(absolute_name)
    except ModuleNotFoundError as exc:
        missing = exc.name or ""
        if missing != "skills" and not missing.startswith("skills.skill_order_to_huading_template"):
            raise
        module = importlib.import_module(module_path)
    return getattr(module, attr_name)


# ---------------------------------------------------------------------------
# 商品名清理
# ---------------------------------------------------------------------------

def clean_product_name(name: str) -> str:
    """
    清理商品名称，去除特殊字符用于匹配

    处理规则：
    - 去除首尾特殊字符（-、/、.等）
    - 去除括号及其内容
    - 去除空格
    """
    import re
    name = name.strip().rstrip('-').rstrip('/').rstrip('.')
    name = re.sub(r'[（(].*[)）]', '', name)
    name = name.strip()
    name = re.sub(r'[^\u4e00-\u9fff\w/]', '', name)
    return name


# ---------------------------------------------------------------------------
# SKUMatcher 类
# ---------------------------------------------------------------------------

class SKUMatcher:
    """
    SKU 匹配器

    用法：
        matcher = SKUMatcher(db_config)
        results, unmatched = matcher.match_batch(items, owner_code)
    """

    def __init__(self, db_config: dict):
        self.db_config = db_config

    def match_batch(self, items: list, owner_code: str) -> Tuple[list, list]:
        """
        SKU 批量匹配 — 调用 tools/_sku_mapper.map_sku_batch

        Args:
            items: 订单商品列表
            owner_code: 货主ID

        Returns:
            (formatted_results, unmatched_items)
        """
        map_sku_batch = _import_skill_attr("tools._sku_mapper", "map_sku_batch")

        results, unmatched_items = map_sku_batch(
            owner_code, items, self.db_config
        )

        formatted_results = []
        for r in results:
            seq = next((item.get("seq", 0) for item in items
                        if item.get("product_name", "") == r.get("product_name", "")
                        or item.get("product_name", "") == r.get("sku_name", "")
                        ), 0)
            formatted_results.append({
                "seq": seq,
                "product_name": r["product_name"],
                "spec": r.get("spec", ""),
                "quantity": r.get("quantity", 0),
                "remark": r.get("remark", ""),
                "sku_code": r["sku_code"],
                "sku_name": r["sku_name"],
                "unit": r["unit"],
                "unit_type": r["unit_type"],
                "product_spec": r.get("product_spec", ""),
                "match_method": r.get("match_method", ""),
                "confidence": r.get("confidence", 1.0),
                "need_confirm": r.get("need_confirm", False),
                "candidates": r.get("candidates", []),
                "original_product_name": r.get("original_product_name", ""),
            })

        return formatted_results, unmatched_items

    def get_unit_info(self, sku_code: str, owner_code: str) -> Dict[str, str]:
        """
        获取 SKU 的单位信息

        Returns:
            {"unit": "件/箱/袋", "unit_type": "大单位/中单位/小单位"}
        """
        try:
            from db.table_names import SKU_TABLE
            import psycopg2

            conn = psycopg2.connect(**self.db_config)
            cur = conn.cursor()

            cur.execute(f"""
                SELECT sku_name, unit, unit_type, conversion_ratio
                FROM {SKU_TABLE}
                WHERE sku_code = %s AND shipper_id = %s
                LIMIT 1
            """, (sku_code, owner_code))
            current_row = cur.fetchone()
            if not current_row:
                conn.close()
                return {"unit": "件", "unit_type": "大单位"}

            current_name, current_unit, current_unit_type, current_ratio = current_row

            if current_unit_type:
                conn.close()
                return {"unit": current_unit or "件", "unit_type": current_unit_type}

            cur.execute(f"""
                SELECT sku_code, conversion_ratio, unit
                FROM {SKU_TABLE}
                WHERE sku_name = %s AND shipper_id = %s
            """, (current_name, owner_code))
            all_rows = cur.fetchall()
            conn.close()

            if len(all_rows) <= 1:
                return {"unit": current_unit or "件", "unit_type": "大单位"}

            ratios = sorted(set(r[1] or 1.0 for r in all_rows))
            if len(ratios) == 1:
                return {"unit": current_unit or "件", "unit_type": "大单位"}

            effective_ratio = current_ratio or 1.0
            if effective_ratio == max(ratios):
                return {"unit": current_unit or "件", "unit_type": "大单位"}
            elif effective_ratio == min(ratios):
                return {"unit": current_unit or "件", "unit_type": "小单位"}
            else:
                return {"unit": current_unit or "件", "unit_type": "中单位"}

        except Exception as e:
            print(f"获取单位信息失败: {e}")
            return {"unit": "件", "unit_type": "大单位"}

    def get_unit_type(self, sku_code: str, owner_code: str) -> str:
        """获取 SKU 的单位类型（大/中/小单位）"""
        return self.get_unit_info(sku_code, owner_code)["unit_type"]

    # ------------------------------------------------------------------
    # 映射对照表生成
    # ------------------------------------------------------------------

    def generate_comparison(self, order_data: Dict, store_info: Dict,
                            sku_results: list, unmatched_items: list) -> Dict[str, Any]:
        """
        生成映射对照表（单门店，人工审核用）

        9列字段：
        - 客户: 商品名称、规格、单位、数量
        - 华鼎: SKU编码、SKU名称、数量、单位、单位类型
        """
        comparison_table = []
        alerts = []

        order_items = order_data.get("items", [])
        order_dict = {item.get("seq", i + 1): item for i, item in enumerate(order_items)}

        for result in sku_results:
            seq = result["seq"]
            order_item = order_dict.get(seq, {})
            row = {
                "seq": seq,
                "customer_product_name": order_item.get("product_name", result.get("product_name", "")),
                "customer_spec": order_item.get("spec", result.get("spec", "")),
                "customer_unit": order_item.get("unit", "件"),
                "customer_quantity": order_item.get("quantity", result.get("quantity", 1)),
                "sku_code": result["sku_code"],
                "sku_name": result["sku_name"],
                "huading_quantity": result.get("quantity", 1),
                "huading_unit": result.get("unit", "件"),
                "unit_type": result.get("unit_type", ""),
                "matched": True,
                "confidence": result.get("confidence", 1.0),
                "match_method": result.get("match_method", ""),
                "candidates": result.get("candidates", []),
                "need_confirm": result.get("need_confirm", False),
            }
            comparison_table.append(row)

            if row["confidence"] < 0.8:
                alerts.append({
                    "type": "low_confidence",
                    "row": seq,
                    "severity": "⚠️",
                    "message": f"第{seq}行SKU匹配置信度{row['confidence']:.0%}，低于80%",
                    "details": {
                        "customer_product_name": row["customer_product_name"],
                        "sku_code": row["sku_code"],
                        "confidence": row["confidence"]
                    }
                })

        for item in unmatched_items:
            seq = item.get("seq", 0)
            row = {
                "seq": seq,
                "customer_product_name": item.get("product_name", ""),
                "customer_spec": item.get("spec", ""),
                "customer_unit": item.get("unit", "件"),
                "customer_quantity": item.get("quantity", 1),
                "sku_code": "",
                "sku_name": "",
                "huading_quantity": "",
                "huading_unit": "",
                "unit_type": "",
                "matched": False,
                "confidence": 0,
                "match_method": "未匹配"
            }
            comparison_table.append(row)
            alerts.append({
                "type": "unmatched",
                "row": seq,
                "severity": "🔴",
                "message": f"第{seq}行商品未匹配到系统SKU",
                "details": {
                    "customer_product_name": row["customer_product_name"],
                    "customer_code": item.get("product_code", "")
                }
            })

        comparison_table.sort(key=lambda x: x["seq"])

        for row in comparison_table:
            if not row["matched"]:
                continue
            if not row["huading_unit"]:
                alerts.append({
                    "type": "empty_field",
                    "row": row["seq"],
                    "severity": "🔴",
                    "message": f"第{row['seq']}行华鼎单位为空",
                    "details": {
                        "customer_product_name": row["customer_product_name"],
                        "field": "huading_unit"
                    }
                })

        total_items = len(comparison_table)
        matched_count = len([r for r in comparison_table if r["matched"]])
        unmatched_count = total_items - matched_count

        return {
            "success": True,
            "comparison_table": comparison_table,
            "alerts": alerts,
            "summary": {
                "total_items": total_items,
                "matched_count": matched_count,
                "unmatched_count": unmatched_count,
                "alert_count": len(alerts),
                "has_critical_alerts": any(a["type"] in ["unmatched", "empty_field"] for a in alerts)
            }
        }

    def generate_comparison_multi(self, order_data: Dict, all_store_results: list) -> Dict:
        """
        为多门店订单生成汇总映射对照表

        9列字段：
        - 订单商品名称、订单商品规格、订单数量、订单单位
        - 匹配SKU编码、SKU名称、数量、单位类型、匹配单位
        """
        all_mappings = []
        total_alert_count = 0
        total_matched_count = 0

        for store_result in all_store_results:
            sku_results = store_result["sku_results"]
            store_items = store_result["items"]
            store_name = store_result["store_name"]

            for idx, sku in enumerate(sku_results):
                confidence = sku.get("confidence", 1.0)
                is_alert = confidence < 0.8
                if is_alert:
                    total_alert_count += 1
                if confidence >= 0.8:
                    total_matched_count += 1

                order_item = store_items[idx] if idx < len(store_items) else {}

                all_mappings.append({
                    "订单商品名称": sku.get("original_product_name", order_item.get("product_name", "")),
                    "订单商品规格": order_item.get("spec", ""),
                    "订单数量": order_item.get("quantity", sku.get("quantity", 0)),
                    "订单单位": order_item.get("unit", "件"),
                    "匹配SKU编码": sku.get("sku_code", ""),
                    "SKU名称": sku.get("sku_name", ""),
                    "数量": sku.get("quantity", 0),
                    "单位类型": sku.get("unit_type", ""),
                    "匹配单位": sku.get("unit", "件"),
                    "store": store_name,
                    "seq": idx + 1,
                    "confidence": confidence,
                    "is_alert": is_alert,
                    "alert_reason": "置信度<80%" if is_alert else "",
                })

            for item in store_result["unmatched_items"]:
                all_mappings.append({
                    "订单商品名称": item.get("product_name", ""),
                    "订单商品规格": item.get("spec", ""),
                    "订单数量": item.get("quantity", 0),
                    "订单单位": item.get("unit", "件"),
                    "匹配SKU编码": "",
                    "SKU名称": "",
                    "数量": "",
                    "单位类型": "",
                    "匹配单位": "",
                    "store": store_name,
                    "seq": "❌",
                    "confidence": 0,
                    "is_alert": True,
                    "alert_reason": "SKU未匹配",
                })

        return {
            "mappings": all_mappings,
            "summary": {
                "total_items": len(all_mappings),
                "matched_count": total_matched_count,
                "alert_count": total_alert_count,
                "unmatched_count": sum(len(r["unmatched_items"]) for r in all_store_results),
                "store_count": len(all_store_results),
            }
        }
