"""
Regression tests for execute() confirmation checkpoints.

These tests avoid live DB/LLM calls by patching the instance and module-level
boundaries that talk to external systems.
"""
import os
import sys
import tempfile


SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SKILL_DIR not in sys.path:
    sys.path.insert(0, SKILL_DIR)

import __init__ as skill_module
from __init__ import OrderToHuadingTemplate


def _make_skill(order_data):
    skill = object.__new__(OrderToHuadingTemplate)
    object.__setattr__(skill, "db_config", {"password": "x"})
    object.__setattr__(skill, "output_dir", tempfile.mkdtemp())
    object.__setattr__(skill, "shipper_id", None)
    object.__setattr__(skill, "warehouse_code_map", {})
    object.__setattr__(skill, "tools_parse", lambda *_args, **_kwargs: order_data)
    object.__setattr__(skill, "tools_transform", lambda data: data)
    object.__setattr__(skill, "_generate_multi_store_template", lambda *_args, **_kwargs: None)
    return skill


def _multi_store_order():
    return {
        "success": True,
        "order_no": "DH-O-MULTI",
        "_multi_store": True,
        "stores": {
            "门店A": {
                "store_name": "门店A",
                "phone": "111",
                "address": "地址A",
                "contact_person": "甲",
                "items": [{"seq": 1, "product_name": "商品A", "quantity": 1, "unit": "件"}],
            },
            "门店B": {
                "store_name": "门店B",
                "phone": "222",
                "address": "地址B",
                "contact_person": "乙",
                "items": [{"seq": 1, "product_name": "商品B", "quantity": 2, "unit": "件"}],
            },
        },
        "items": [
            {"seq": 1, "_store_name": "门店A", "product_name": "商品A", "quantity": 1, "unit": "件"},
            {"seq": 1, "_store_name": "门店B", "product_name": "商品B", "quantity": 2, "unit": "件"},
        ],
    }


def test_single_confirmed_store_does_not_apply_to_all_multi_store_entries() -> None:
    order_data = _multi_store_order()
    skill = _make_skill(order_data)
    object.__setattr__(
        skill,
        "_match_sku",
        lambda items, owner_code: (
            [{"product_name": items[0]["product_name"], "sku_code": "SKU", "sku_name": "SKU", "quantity": items[0]["quantity"], "unit": "件", "unit_type": "大单位", "confidence": 1.0}],
            [],
        ),
    )

    original_match_store = skill_module._call_match_store
    try:
        skill_module._call_match_store = lambda **_kwargs: {
            "need_confirm": True,
            "store_name_submitted": "门店B",
            "candidates": [
                {
                    "store_code": "B001",
                    "store_name": "门店B-候选",
                    "owner_code": "OWNER-B",
                    "similarity": 0.7,
                    "match_type": "fuzzy",
                    "match_method": "测试候选",
                }
            ],
        }

        result = skill.execute(
            order_input="ignored",
            order_type="text",
            order_data_cache=order_data,
            confirmed_store={
                "_store_key": "门店A",
                "store_code": "A001",
                "store_name": "门店A-确认",
                "owner_code": "OWNER-A",
                "match_type": "exact",
            },
        )
    finally:
        skill_module._call_match_store = original_match_store

    assert result["need_store_confirm"], result
    assert result["store_name_submitted"] == "门店B", result
    assert result["order_data_cache"]["_confirmed_stores"]["门店A"]["store_code"] == "A001", result


def test_sku_mapping_requires_confirmation_before_template_generation() -> None:
    order_data = {
        "success": True,
        "order_no": "DH-O-SKU",
        "stores": {
            "门店A": {
                "store_name": "门店A",
                "items": [{"seq": 1, "product_name": "未知商品", "quantity": 1, "unit": "件"}],
            }
        },
        "items": [{"seq": 1, "product_name": "未知商品", "quantity": 1, "unit": "件"}],
    }
    skill = _make_skill(order_data)
    generated = {"called": False}
    object.__setattr__(skill, "_generate_multi_store_template", lambda *_args, **_kwargs: generated.update(called=True))
    object.__setattr__(skill, "_match_sku", lambda items, _owner_code: ([], [items[0]]))

    # v5.15.2: confirmed_store 路径会调 _call_match_store 做对比，需要 mock
    original_match_store = skill_module._call_match_store
    try:
        skill_module._call_match_store = lambda **_kwargs: {
            "store_code": "A001",
            "store_name": "门店A-确认",
            "owner_code": "OWNER-A",
            "similarity": 1.0,
            "match_type": "exact",
        }

        result = skill.execute(
            order_input="ignored",
            order_type="text",
            order_data_cache=order_data,
            confirmed_store={
                "_store_key": "门店A",
                "store_code": "A001",
                "store_name": "门店A-确认",
                "owner_code": "OWNER-A",
                "match_type": "exact",
            },
        )
    finally:
        skill_module._call_match_store = original_match_store

    assert result["need_sku_confirm"], result
    assert not generated["called"], result
    assert result["unmatched_items"][0]["product_name"] == "未知商品", result


def main() -> None:
    test_single_confirmed_store_does_not_apply_to_all_multi_store_entries()
    test_sku_mapping_requires_confirmation_before_template_generation()
    print("PASSED execute confirmation flow regressions")


if __name__ == "__main__":
    main()
