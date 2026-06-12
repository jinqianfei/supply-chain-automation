"""
Regression tests for execute() confirmation checkpoints.

These tests avoid live DB/LLM calls by patching the instance and module-level
boundaries that talk to external systems.

Updated for Phase 8 refactored architecture: uses StoreMatcher/SKUMatcher instances.
"""
import os
import sys
import tempfile


SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SKILL_DIR not in sys.path:
    sys.path.insert(0, SKILL_DIR)

import __init__ as skill_module
from __init__ import OrderToHuadingTemplate


class MockStoreMatcher:
    """Mock StoreMatcher that returns configurable results."""

    def __init__(self, process_result=None):
        self._process_result = process_result or {"success": True, "all_store_results": [], "confirmed_stores": {}}

    def process_all_stores(self, order_data, confirmed_stores, sku_matcher=None,
                           session_id="", emit_event=None):
        return self._process_result

    @staticmethod
    def find_confirmation(confirmed_stores, store_key, store_name=None):
        return confirmed_stores.get(store_key)

    @staticmethod
    def is_auto_confirmed(match_result):
        return False

    @staticmethod
    def cache_order(order_data, confirmed_stores):
        return order_data

    def match(self, store_name, **kwargs):
        return {"store_code": "X", "store_name": store_name, "owner_code": "OWNER-X", "similarity": 1.0}


class MockSKUMatcher:
    """Mock SKUMatcher that returns configurable results."""

    def __init__(self, match_result=None):
        self._match_result = match_result or ([], [])

    def match_batch(self, items, owner_code):
        return self._match_result

    def generate_comparison_multi(self, order_data, all_store_results):
        return {"summary": {"alert_count": 0}, "items": []}


def _make_skill(order_data, store_result=None, sku_match_result=None):
    skill = object.__new__(OrderToHuadingTemplate)
    object.__setattr__(skill, "db_config", {"password": "x"})
    object.__setattr__(skill, "output_dir", tempfile.mkdtemp())
    object.__setattr__(skill, "shipper_id", None)
    object.__setattr__(skill, "warehouse_code_map", {})
    object.__setattr__(skill, "tools_parse", lambda *_args, **_kwargs: order_data)
    object.__setattr__(skill, "tools_transform", lambda data: data)
    object.__setattr__(skill, "_generate_multi_store_template", lambda *_args, **_kwargs: None)
    object.__setattr__(skill, "_store_matcher", MockStoreMatcher(store_result))
    object.__setattr__(skill, "_sku_matcher", MockSKUMatcher(sku_match_result))
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
    """
    v5.15.4 P1: Multi-store confirmed_store leak fix.
    When 门店A is confirmed but 门店B is pending, execute should return need_store_confirm.
    """
    order_data = _multi_store_order()

    # process_all_stores returns: 门店A confirmed, 门店B pending
    store_result = {
        "success": False,
        "need_store_confirm": True,
        "batch_mode": True,
        "all_store_matches": [
            {"store_key": "门店A", "store_name_submitted": "门店A", "items_count": 1,
             "status": "confirmed", "is_confirmed": True, "is_auto_confirmed": True,
             "matched_store": {"store_code": "A001", "store_name": "门店A-确认", "owner_code": "OWNER-A"}},
            {"store_key": "门店B", "store_name_submitted": "门店B", "items_count": 1,
             "status": "pending", "is_confirmed": False, "is_auto_confirmed": False,
             "matched_store": {"store_code": "B001", "store_name": "门店B-候选", "owner_code": "OWNER-B",
                              "similarity": 0.7},
             "candidates": [{"store_code": "B001", "store_name": "门店B-候选", "owner_code": "OWNER-B",
                            "similarity": 0.7, "match_type": "fuzzy"}]},
        ],
        "pending_store_keys": ["门店B"],
        "pending_count": 1,
        "confirmed_count": 1,
        "failed_count": 0,
        "failed_stores": [],
        "confirmed_stores": {"门店A": {"_store_key": "门店A", "store_code": "A001",
                                       "store_name": "门店A-确认", "owner_code": "OWNER-A", "match_type": "exact"}},
        "order_data_cache": order_data,
        "store_name_submitted": "门店B",
        "matched_store": {"store_code": "B001", "store_name": "门店B-候选", "owner_code": "OWNER-B", "similarity": 0.7},
        "candidates": [{"store_code": "B001", "store_name": "门店B-候选", "owner_code": "OWNER-B",
                        "similarity": 0.7, "match_type": "fuzzy"}],
        "message": "共 2 个门店：1 已确认，1 待确认，0 失败。请确认所有门店后继续",
    }

    skill = _make_skill(order_data, store_result=store_result)

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

    assert result.get("need_store_confirm"), f"Expected need_store_confirm=True, got: {result}"
    assert result.get("store_name_submitted") == "门店B", f"Expected pending store 门店B, got: {result.get('store_name_submitted')}"


def test_sku_mapping_requires_confirmation_before_template_generation() -> None:
    """
    When all stores confirmed but SKU has unmatched items, execute should return need_sku_confirm.
    """
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

    # All stores confirmed → Phase B runs → SKU matching happens
    store_result = {
        "success": True,
        "all_store_results": [
            {"store_info": {"store_code": "A001", "store_name": "门店A", "owner_code": "OWNER-A"},
             "store_name": "门店A",
             "sku_results": [],
             "unmatched_items": [{"seq": 1, "product_name": "未知商品", "quantity": 1, "unit": "件", "_store": "门店A"}],
             "items": [{"seq": 1, "product_name": "未知商品", "quantity": 1, "unit": "件"}]},
        ],
        "confirmed_stores": {"门店A": {"store_code": "A001", "store_name": "门店A", "owner_code": "OWNER-A"}},
    }

    generated = {"called": False}
    skill = _make_skill(order_data, store_result=store_result)
    object.__setattr__(skill, "_generate_multi_store_template", lambda *_args, **_kwargs: generated.update(called=True))

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

    assert result.get("need_sku_confirm"), f"Expected need_sku_confirm=True, got: {result}"
    assert not generated["called"], "Template should NOT be generated before SKU confirmation"
    unmatched = result.get("unmatched_items", [])
    assert len(unmatched) > 0 and unmatched[0]["product_name"] == "未知商品", f"Expected unmatched 未知商品, got: {unmatched}"


def main() -> None:
    test_single_confirmed_store_does_not_apply_to_all_multi_store_entries()
    print("  ✅ test_single_confirmed_store_does_not_apply_to_all_multi_store_entries")
    test_sku_mapping_requires_confirmation_before_template_generation()
    print("  ✅ test_sku_mapping_requires_confirmation_before_template_generation")
    print("PASSED execute confirmation flow regressions")


if __name__ == "__main__":
    main()
