#!/usr/bin/env python3
"""
P1 Fix Test: _confirmed_store_for 多门店隔离

Bug: 当只有 1 个门店的 confirmed_store 时，所有门店都拿到了同一个 store_info
Fix: 移除 _confirmed_store_for 中的 _store_key fallback，防止跨门店泄漏
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from __init__ import _confirmed_store_for, _merge_confirmed_store


def test_no_cross_store_leakage():
    """核心测试: 门店A的确认信息不应泄漏到门店B"""
    # 模拟: AI 只确认了门店A（单个 confirmed_store dict）
    confirmed_stores = _merge_confirmed_store({}, {
        "store_code": "S001",
        "store_name": "沧州XX店",
        "owner_code": "HZ001",
        "_store_key": "沧州XX店",
        "store_name_submitted": "沧州XX店",
    })
    
    # 门店A 应该能找到确认信息
    store_a = _confirmed_store_for(confirmed_stores, "沧州XX店", "沧州XX店")
    assert store_a is not None, "门店A 应该找到确认信息"
    assert store_a.get("store_code") == "S001", f"门店A store_code 应为 S001, got {store_a.get('store_code')}"
    
    # 门店B 不应该找到门店A的确认信息（这是 bug 的核心）
    store_b = _confirmed_store_for(confirmed_stores, "任丘XX店", "任丘XX店")
    assert store_b is None, f"门店B 不应该拿到门店A的确认信息! got: {store_b}"
    print("✅ test_no_cross_store_leakage PASSED")


def test_alias_key_lookup():
    """别名查找: 当 confirmed_stores 用不同 key 存储时，原 key 仍能查到"""
    # AI 可能用 store_name 作为 key（而不是原始 store_key）
    confirmed_stores = {
        "张三烤鱼": {
            "store_code": "S002",
            "store_name": "张三烤鱼(旗舰店)",
            "owner_code": "HZ002",
            "_store_key": "门店A",
            "store_name_submitted": "张三烤鱼",
        }
    }
    
    # 用原始 store_key 查找 → 不应找到（因为没有 "门店A" key，且 store_name_submitted="张三烤鱼" != "门店A"）
    result = _confirmed_store_for(confirmed_stores, "门店A", "门店A")
    # 这个查找应该返回 None（正确的隔离行为）
    assert result is None, f"用不匹配的 key 不应找到确认信息! got: {result}"
    
    # 用 store_name_submitted 查找 → 应找到
    result2 = _confirmed_store_for(confirmed_stores, "张三烤鱼", "张三烤鱼")
    assert result2 is not None, "用 store_name_submitted 应该找到"
    assert result2.get("store_code") == "S002"
    print("✅ test_alias_key_lookup PASSED")


def test_batch_confirmed_stores():
    """批量确认: 每个门店独立确认，互不干扰"""
    confirmed_stores = _merge_confirmed_store({}, {
        "confirmed_stores": {
            "沧州XX店": {
                "store_code": "S001",
                "store_name": "沧州XX店",
                "owner_code": "HZ001",
            },
            "任丘XX店": {
                "store_code": "S002",
                "store_name": "任丘XX店",
                "owner_code": "HZ002",
            },
        }
    })
    
    store_a = _confirmed_store_for(confirmed_stores, "沧州XX店", "沧州XX店")
    store_b = _confirmed_store_for(confirmed_stores, "任丘XX店", "任丘XX店")
    
    assert store_a is not None and store_a.get("owner_code") == "HZ001"
    assert store_b is not None and store_b.get("owner_code") == "HZ002"
    print("✅ test_batch_confirmed_stores PASSED")


def test_submitted_name_alias():
    """提交名称别名: store_name_submitted 作为候选名可正确匹配"""
    confirmed_stores = {
        "some_ai_key": {
            "store_code": "S003",
            "store_name": "李四烧烤(总店)",
            "owner_code": "HZ003",
            "store_name_submitted": "李四烧烤",
        }
    }
    
    # 用 store_name_submitted 作为 store_name 查找 → 应找到
    result = _confirmed_store_for(confirmed_stores, "other_key", "李四烧烤")
    assert result is not None, "用 store_name_submitted 作为 store_name 应找到"
    assert result.get("store_code") == "S003"
    
    # 用完全不同的名称查找 → 不应找到
    result2 = _confirmed_store_for(confirmed_stores, "other_key", "王五麻辣烫")
    assert result2 is None, "用不相关的名称不应找到"
    print("✅ test_submitted_name_alias PASSED")


if __name__ == "__main__":
    test_no_cross_store_leakage()
    test_alias_key_lookup()
    test_batch_confirmed_stores()
    test_submitted_name_alias()
    print(f"\n🎉 All {4} tests PASSED — P1 multi-store fix verified!")
