"""
learning/feedback_parser.py — 用户反馈解析器

从 __init__.py._parse_user_feedback 提取，独立函数。
不 import skill 的任何代码。

职责：解析用户对 SKU 映射结果的自然语言反馈，提取结构化修改指令。
"""
import re
import time
from typing import Dict, Any, List, Optional


def parse_user_feedback(user_message: str, mapping_result: Dict[str, Any],
                        current_order_data: Dict = None,
                        session_id: str = "unknown",
                        emit_event=None) -> Dict[str, Any]:
    """
    解析用户反馈，返回结构化的修改指令

    Args:
        user_message: 用户的反馈消息
        mapping_result: 当前映射结果（comparison_table + alerts）
        current_order_data: 当前订单数据（可选）
        session_id: 会话 ID（用于事件 emit）
        emit_event: 可选的事件发射函数 emit_event(event_name, data)

    Returns:
        {
            "action": "confirm" | "modify" | "ask" | "cancel",
            "modifications": [...],
            "summary": "对修改指令的中文描述"
        }
    """
    try:
        table = mapping_result.get("comparison_table", [])
        alerts = mapping_result.get("alerts", [])

        user_msg = user_message.strip()

        # 确认通过
        confirm_keywords = ["没问题", "确认", "通过", "生成吧", "可以", "好的", "确认生成"]
        if any(kw in user_msg for kw in confirm_keywords):
            return {
                "action": "confirm",
                "modifications": [],
                "summary": "用户确认通过"
            }

        # 取消
        cancel_keywords = ["取消", "算了", "不要了"]
        if any(kw in user_msg for kw in cancel_keywords):
            return {
                "action": "cancel",
                "modifications": [],
                "summary": "用户取消操作"
            }

        # 定向修改
        modifications = []

        row_pattern = r'第(\d+)行'
        field_pattern = r'(SKU|系统SKU|华鼎单位|单位类型|商品名称|数量|规格)'
        value_pattern = r'(?:应该是|改成|是)([^(|\n]+)'

        row_matches = re.findall(row_pattern, user_msg)
        if row_matches:
            for row_num in row_matches:
                mod = {"row": int(row_num), "field": "", "old_value": "", "new_value": ""}

                field_match = re.search(field_pattern, user_msg)
                if field_match:
                    field = field_match.group(1)
                    field_map = {
                        "SKU": "sku_code",
                        "华鼎SKU编码": "sku_code",
                        "SKU名称": "sku_name",
                        "华鼎单位": "huading_unit",
                        "单位类型": "unit_type",
                        "客户商品名称": "customer_product_name",
                        "数量": "quantity",
                        "规格": "customer_spec"
                    }
                    mod["field"] = field_map.get(field, field)

                value_match = re.search(value_pattern, user_msg)
                if value_match:
                    mod["new_value"] = value_match.group(1).strip()

                if mod["field"] and mod["new_value"]:
                    modifications.append(mod)

        # 全局修改
        all_pattern = r'所有(华鼎单位|单位类型|SKU|数量)(?:都)?改成(.+)'
        all_match = re.search(all_pattern, user_msg)
        if all_match:
            field = all_match.group(1)
            value = all_match.group(2).strip()
            field_map = {
                "华鼎单位": "huading_unit",
                "单位类型": "unit_type",
                "SKU": "sku_code",
                "华鼎SKU编码": "sku_code",
                "数量": "quantity"
            }
            modifications.append({
                "row": "all",
                "field": field_map.get(field, field),
                "old_value": "",
                "new_value": value
            })

        if modifications:
            if emit_event:
                try:
                    emit_event("user_modified", {
                        "session_id": session_id,
                        "timestamp": time.time(),
                        "modifications": modifications,
                        "modification_count": len(modifications),
                        "user_response_text": user_message,
                    })
                except Exception:
                    pass
            return {
                "action": "modify",
                "modifications": modifications,
                "summary": f"检测到{len(modifications)}项修改"
            }

        return {
            "action": "ask",
            "modifications": [],
            "summary": "无法理解用户反馈，请重述",
            "question": user_msg
        }

    except Exception as e:
        print(f"解析用户反馈失败: {e}")
        return {
            "action": "ask",
            "modifications": [],
            "summary": f"解析失败: {str(e)}"
        }
