"""
字段校正工具 - 用规则库校正LLM解析结果，输出统一结构化JSON

设计：
- 输入：LLM解析的原始JSON（可能包含 stores{} 或旧格式 store_info+items）
- 处理：加载客户YAML规则 → 字段名标准化 → 值校验 → 输出统一JSON
- 输出：统一结构化JSON（含多门店）

规则库位置：field_mapping/rules/{客户名}.yaml
"""
import os
import re
import json
import yaml
from typing import Optional, Dict, Any, List


# =============================================================================
# 通用函数
# =============================================================================

def clean_text(text):
    """清洗文本中的各种空白字符"""
    if not text:
        return ""
    text = str(text)
    text = text.strip()
    text = re.sub(r'[\t\u00a0\u3000\u200b-\u200f\ufeff]+', '', text)
    text = text.replace(' ', '')
    return text


# =============================================================================
# 统一JSON schema 字段
# =============================================================================

UNIFIED_ORDER_SCHEMA = {
    "order_date": str,
    "store_name": str,
    "store_phone": str,
    "store_address": str,
    "warehouse": str,
    "raw_order_no": str,
    "extra_notes": str,
    "shipper_name": str,
}

ITEM_SCHEMA = {
    "product_name": str,
    "product_spec": str,
    "unit": str,
    "quantity": int,
    "remark": str,
    "product_code": str,
}


def transform(llm_result: Dict, customer: str = "default") -> Dict[str, Any]:
    """
    将LLM解析结果校正为统一结构化JSON

    Args:
        llm_result: LLM解析的原始结果（来自 order_parser 的输出）
        customer: 客户标识，用于加载对应规则

    Returns:
        {
            "success": bool,
            "stores": {...},        # 多门店统一JSON
            "items": [...],        # 合并所有门店商品（兼容）
            "confidence": float,
            "warnings": [...],
            "errors": [...],
            "_customer": str,
            "_rule_file": str,
        }
    """
    # 加载规则
    rules = _load_rules(customer)
    field_aliases = rules.get("field_aliases", {})
    validation = rules.get("validation", {})
    customer_name = rules.get("customer_name", customer)

    warnings = []
    errors = []

    # ========== 提取原始 stores 或单个 store ==========
    raw_stores = llm_result.get("stores", {})
    if not raw_stores:
        # 旧格式：只有一个门店
        store_name = llm_result.get("store_name", "")
        if store_name:
            raw_stores = {store_name: {
                "store_name": store_name,
                "contact_person": llm_result.get("contact_person", ""),
                "phone": llm_result.get("phone", ""),
                "address": llm_result.get("address", ""),
                "order_no": llm_result.get("order_no", ""),
                "shipper_name": llm_result.get("shipper_name", ""),
                "warehouse_name": llm_result.get("warehouse_name", ""),
                "items": llm_result.get("items", []),
            }}

    if not raw_stores:
        return {
            "success": False,
            "stores": {},
            "items": [],
            "confidence": llm_result.get("confidence", 0),
            "warnings": ["未找到任何门店数据"],
            "errors": ["缺少门店信息"],
            "_customer": customer,
            "_rule_file": f"{customer}.yaml",
        }

    # ========== 转换每个门店 ==========
    unified_stores = {}
    all_items = []

    for store_key, store_data in raw_stores.items():
        unified_store, store_warnings, store_errors = _transform_store(
            store_data, field_aliases
        )
        warnings.extend(store_warnings)
        errors.extend(store_errors)

        if unified_store["store_name"]:
            unified_stores[unified_store["store_name"]] = unified_store
            all_items.extend(unified_store["items"])

    # ========== 规则库后的二次校验 ==========
    validation_errors = _validate_after_transform(unified_stores, validation)
    errors.extend(validation_errors)

    # ========== 设置多门店标记 ==========
    store_count = len(unified_stores)
    is_multi = store_count > 1

    return {
        "success": len(errors) == 0,
        "stores": unified_stores,
        "items": all_items,
        "confidence": llm_result.get("confidence", 0),
        "warnings": warnings,
        "errors": errors,
        "_customer": customer_name,
        "_rule_file": f"{customer}.yaml" if customer != "default" else "default.yaml",
        "_multi_store": is_multi,
        "_store_count": store_count,
    }


def _transform_store(store_data: Dict, field_aliases: Dict) -> tuple:
    """
    转换单个门店的数据
    返回: (unified_store_dict, warnings, errors)
    """
    warnings = []
    errors = []
    unified_items = []

    # 字段名标准化（store层级字段）
    raw_fields = {k: v for k, v in store_data.items()
                  if not k.startswith("_") and k not in ["items", "order_no", "contact_person", "phone", "address", "warehouse_name"]}

    standardized = {}
    for raw_name, raw_value in raw_fields.items():
        std_name = _find_std_field(raw_name, field_aliases)
        if std_name:
            standardized[std_name] = raw_value
        else:
            warnings.append(f"未知字段名: {raw_name}")

    # 门店基本信息
    store_name = standardized.get("store_name", store_data.get("store_name", ""))
    for prefix in ['河北-', '天津-', '沧州-', '创宇-', '盐城创宇-']:
        if store_name.startswith(prefix):
            store_name = store_name[len(prefix):]
            break

    # 值校正（correction规则 - 已废弃，保留接口）
    # for field, corrections in correction.items():
    #     if field in standardized and corrections:
    #         val = str(standardized[field])
    #         for old_val, new_val in corrections.items():
    #             if val == old_val or val == str(old_val):
    #                 standardized[field] = new_val
    #                 break

    # 处理 items
    raw_items = store_data.get("items", [])
    if not isinstance(raw_items, list):
        raw_items = []

    for idx, item in enumerate(raw_items):
        if not isinstance(item, dict):
            continue

        # 字段名标准化（item层级）
        item_std = {}
        for k, v in item.items():
            if k.startswith("_") or k in ["seq", "confidence"]:
                continue
            std_name = _find_std_field(k, field_aliases)
            if std_name:
                item_std[std_name] = v

        # 商品名（多个可能的字段名）
        product_name = _get_first_non_empty(
            item_std, ["product_name", "product", "goods", "name", "品名", "商品名称"], ""
        )

        if not product_name or product_name == "nan":
            warnings.append(f"商品明细缺少商品名称，跳过第{idx + 1}条")
            continue

        # 规格
        spec = _get_first_non_empty(item_std, ["spec", "product_spec", "规格", "规格型号"], "")

        # 单位
        unit = _get_first_non_empty(item_std, ["unit", "单位", "销售单位", "件", "箱"], "件")

        # 数量
        raw_qty = _get_first_non_empty(item_std, ["quantity", "qty", "数量", "件数"], 0)
        quantity = _safe_int(raw_qty)

        if quantity <= 0:
            warnings.append(f"商品「{product_name}」数量异常({quantity})，已设为0")

        unified_items.append({
            "seq": item.get("seq", idx + 1),
            "product_name": clean_text(product_name),
            "spec": clean_text(spec),
            "product_spec": clean_text(spec),
            "unit": clean_text(unit),
            "quantity": quantity,
            "remark": clean_text(item_std.get("remark", "")),
            "product_code": str(item_std.get("product_code", "")).strip(),
        })

    # 校验必填项
    if not store_name:
        errors.append("缺少门店名称")

    return {
        "store_name": store_name,
        "phone": standardized.get("store_phone", store_data.get("phone", "")),
        "store_phone": standardized.get("store_phone", store_data.get("phone", "")),
        "address": standardized.get("store_address", store_data.get("address", "")),
        "store_address": standardized.get("store_address", store_data.get("address", "")),
        "warehouse": standardized.get("warehouse", store_data.get("warehouse_name", "")),
        "raw_order_no": store_data.get("order_no", ""),
        "extra_notes": standardized.get("extra_notes", ""),
        "shipper_name": standardized.get("shipper_name", store_data.get("shipper_name", "")),
        "contact_person": store_data.get("contact_person", ""),
        "items": unified_items,
    }, warnings, errors


def _load_rules(customer: str = "default") -> dict:
    """加载客户对应的字段映射规则（含自学习自动积累的别名）"""
    rules_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "field_mapping", "rules"
    )

    # 尝试客户规则
    for fname in [f"{customer}.yaml", f"{customer}.yml"]:
        path = os.path.join(rules_dir, fname)
        if os.path.exists(path):
            with open(path, "r") as f:
                rules = yaml.safe_load(f) or {}
                return _merge_auto_aliases(rules, rules_dir)

    # 尝试客户名模糊匹配
    if os.path.exists(rules_dir):
        for fname in os.listdir(rules_dir):
            if fname.startswith(".") or fname.startswith("_") or fname == "field_aliases_auto.yaml":
                continue
            if not fname.endswith((".yaml", ".yml")):
                continue
            path = os.path.join(rules_dir, fname)
            try:
                with open(path, "r") as f:
                    rule = yaml.safe_load(f) or {}
                rule_cname = rule.get("customer_name", "")
                if rule_cname and rule_cname in customer:
                    return _merge_auto_aliases(rule, rules_dir)
            except Exception:
                continue

    # 兜底默认规则
    default_path = os.path.join(rules_dir, "default.yaml")
    if os.path.exists(default_path):
        with open(default_path, "r") as f:
            rules = yaml.safe_load(f) or {}
            return _merge_auto_aliases(rules, rules_dir)

    rules = {"field_aliases": {}, "validation": {}}
    return _merge_auto_aliases(rules, rules_dir)


def _merge_auto_aliases(rules: dict, rules_dir: str) -> dict:
    """合并自学习自动积累的字段别名（优先级高于默认规则）"""
    auto_path = os.path.join(rules_dir, "field_aliases_auto.yaml")
    if not os.path.exists(auto_path):
        return rules
    try:
        with open(auto_path, "r") as f:
            auto_data = yaml.safe_load(f) or {}
        auto_aliases = auto_data.get("aliases", [])
        if not auto_aliases:
            return rules
        # 确保 field_aliases 存在
        if "field_aliases" not in rules:
            rules["field_aliases"] = {}
        # 合并：auto aliases 追加到对应标准字段的别名列表前面（高优先级）
        for item in auto_aliases:
            raw_name = item.get("raw_field_name", "")
            std_field = item.get("standard_field", "")
            if not raw_name or not std_field:
                continue
            if std_field not in rules["field_aliases"]:
                rules["field_aliases"][std_field] = []
            # 插入到列表开头（高优先级）
            if raw_name not in rules["field_aliases"][std_field]:
                rules["field_aliases"][std_field].insert(0, raw_name)
        return rules
    except Exception:
        return rules


def _find_std_field(raw_name: str, field_aliases: Dict) -> Optional[str]:
    """将LLM输出的字段名映射到标准字段名"""
    raw_lower = raw_name.lower().strip()
    for std_field, aliases in field_aliases.items():
        if raw_lower == std_field.lower():
            return std_field
        for alias in aliases:
            if raw_lower == alias.lower():
                return std_field
    return None


def _get_first_non_empty(data: Dict, keys: List[str], default):
    """从字典中查找第一个非空值"""
    for k in keys:
        v = data.get(k)
        if v is not None and v != "" and v != "nan":
            return v
    return default


def _safe_int(value) -> int:
    """安全转换为整数"""
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        cleaned = re.sub(r'[^0-9.]', '', value)
        try:
            return int(float(cleaned)) if cleaned else 0
        except (ValueError, TypeError):
            return 0
    return 0


def _validate_after_transform(stores: Dict, validation: Dict) -> List[str]:
    """二次校验：检查必填字段"""
    errors = []
    required_fields = validation.get("required", ["product_name", "quantity"])

    for store_name, store_data in stores.items():
        items = store_data.get("items", [])
        if not store_name:
            errors.append("缺少门店名称")
        if not items:
            errors.append(f"门店「{store_name}」没有商品明细")
            continue
        for idx, item in enumerate(items):
            for field in required_fields:
                if field == "product_name" and not item.get("product_name"):
                    errors.append(f"门店「{store_name}」第{idx + 1}条商品缺少商品名称")
                elif field == "quantity" and not item.get("quantity", 0) > 0:
                    errors.append(f"门店「{store_name}」第{idx + 1}条商品数量异常")
    return errors


def list_available_rules() -> List[Dict]:
    """列出所有可用的规则配置"""
    rules_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "field_mapping", "rules")
    if not os.path.exists(rules_dir):
        return []

    rules = []
    for fname in sorted(os.listdir(rules_dir)):
        if not fname.endswith((".yaml", ".yml")) or fname.startswith("_"):
            continue
        path = os.path.join(rules_dir, fname)
        try:
            with open(path, "r") as f:
                rule = yaml.safe_load(f) or {}
            rules.append({
                "filename": fname,
                "customer_name": rule.get("customer_name", fname.replace(".yaml", "")),
                "description": rule.get("description", ""),
                "field_count": len(rule.get("field_aliases", {})),
            })
        except Exception:
            continue
    return rules
