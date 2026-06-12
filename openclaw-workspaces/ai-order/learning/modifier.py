"""
learning/modifier.py — 映射结果修改器

从 __init__.py._apply_modifications 提取，独立函数。
不 import skill 的任何代码。

职责：根据用户反馈的结构化修改指令，更新映射对照表。
"""
from typing import Dict, Any, List, Optional, Callable


def apply_modifications(mapping_result: Dict[str, Any], modifications: list,
                        sku_results: list = None, owner_code: str = "",
                        get_unit_info_fn: Callable = None) -> Dict[str, Any]:
    """
    应用修改到映射结果

    Args:
        mapping_result: 当前映射结果（comparison_table + alerts + summary）
        modifications: 修改指令列表 [{"row": int|"all", "field": str, "new_value": str}]
        sku_results: SKU 匹配结果列表（可选，用于重新获取单位信息）
        owner_code: 货主 ID（可选，用于单位查询）
        get_unit_info_fn: 可选函数 (sku_code, owner_code) -> {"unit": str, "unit_type": str}

    Returns:
        更新后的 mapping_result
    """
    comparison_table = mapping_result["comparison_table"]

    for mod in modifications:
        row = mod["row"]
        field = mod["field"]
        new_value = mod["new_value"]

        if row == "all":
            for item in comparison_table:
                if field == "unit_type" and item["matched"]:
                    sku_code = item["sku_code"]
                    if get_unit_info_fn and owner_code:
                        unit_info = get_unit_info_fn(sku_code, owner_code)
                        item["unit_type"] = new_value
                        item["huading_unit"] = unit_info["unit"]
                    else:
                        item["unit_type"] = new_value
                elif field in item:
                    item[field] = new_value
        else:
            for item in comparison_table:
                if item["seq"] == row:
                    if field == "unit_type" and item["matched"]:
                        sku_code = item["sku_code"]
                        if get_unit_info_fn and owner_code:
                            unit_info = get_unit_info_fn(sku_code, owner_code)
                            item["unit_type"] = new_value
                            item["huading_unit"] = unit_info["unit"]
                        else:
                            item["unit_type"] = new_value
                    elif field in item:
                        item[field] = new_value
                    break

    mapping_result["comparison_table"] = comparison_table

    # 重新检查告警
    alerts = []
    for row_item in comparison_table:
        if not row_item["matched"]:
            alerts.append({
                "type": "unmatched",
                "row": row_item["seq"],
                "severity": "🔴",
                "message": f"第{row_item['seq']}行商品未匹配到系统SKU"
            })
        elif not row_item["huading_unit"]:
            alerts.append({
                "type": "empty_field",
                "row": row_item["seq"],
                "severity": "🔴",
                "message": f"第{row_item['seq']}行华鼎单位为空"
            })

    mapping_result["alerts"] = alerts
    mapping_result["summary"]["alert_count"] = len(alerts)
    mapping_result["summary"]["has_critical_alerts"] = any(
        a["type"] in ["unmatched", "empty_field"] for a in alerts
    )

    return mapping_result
