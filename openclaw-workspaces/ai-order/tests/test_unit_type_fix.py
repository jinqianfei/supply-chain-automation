#!/usr/bin/env python3
"""v5.12.0 单位类型选择修复 — 端到端验证"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'skills', 'skill_order_to_huading_template'))

from tools._sku_mapper import _resolve_unit_type, map_sku_batch

DB_CONFIG = {
    "host": "agenthub-db.cjys0msc4x8s.ap-southeast-1.rds.amazonaws.com",
    "port": 5432, "database": "neo", "user": "agenthub",
    "password": "Agenthub_RDS_2026!c9fce7060773"
}

print("=" * 60)
print("Part 1: _resolve_unit_type 单元测试")
print("=" * 60)

# (sku_code, sku_name, unit, unit_type, conversion_ratio, product_spec, customer_code)
rows_2 = [
    ("SK_S", "1000塑杯", "袋", "小单位", 1.0, "50个", ""),
    ("SK_L", "1000塑杯", "件", "大单位", 12.0, "50个*12袋/件", ""),
]
rows_3 = [
    ("SK_S", "三ratio", "个", "小单位", 1.0, "", ""),
    ("SK_M", "三ratio", "盒", "中单位", 6.0, "", ""),
    ("SK_L", "三ratio", "箱", "大单位", 60.0, "", ""),
]
rows_single = [
    ("SK_ONLY", "独立商品", "件", "大单位", 1.0, "", ""),
]

unit_tests = [
    # (rows, qty, unit, expected_type, desc)
    # 单位精确匹配
    (rows_2, 5, "件",  "大单位", "单位=件 → 匹配大单位"),
    (rows_2, 5, "袋",  "小单位", "单位=袋 → 匹配小单位"),
    (rows_2, 12,"件",  "大单位", "单位=件 → 匹配大单位"),
    (rows_2, 100,"袋", "小单位", "单位=袋 → 匹配小单位"),
    (rows_3, 1, "个",  "小单位", "3SKU 单位=个 → 小"),
    (rows_3, 6, "盒",  "中单位", "3SKU 单位=盒 → 中"),
    (rows_3, 60,"箱",  "大单位", "3SKU 单位=箱 → 大"),
    # 单位匹配不上 → 用第一个SKU的unit_type
    (rows_2, 5, "",   "小单位", "无单位 → 第一个SKU(小单位)"),
    (rows_2, 12,"",   "小单位", "无单位 → 第一个SKU(小单位)"),
    (rows_2, 5, "箱", "小单位", "单位=箱匹配不上 → 第一个SKU(小单位)"),
    # 单SKU
    (rows_single, 5, "", "大单位", "单SKU → 唯一"),
    (rows_single, 5, "件","大单位", "单SKU → 唯一"),
]

passed = 0
for rows, qty, unit, expected, desc in unit_tests:
    selected, need_confirm, _ = _resolve_unit_type(rows, qty, unit)
    actual = selected[3]
    ok = actual == expected
    if ok: passed += 1
    print(f"  {'✅' if ok else '❌'} {desc}: got={actual}")

print(f"\n  单元测试: {passed}/{len(unit_tests)} passed")

print()
print("=" * 60)
print("Part 2: 端到端真实订单测试")
print("=" * 60)

# 订单 #1: 洪洪通 1店1项
# GT: SK231013000200 大单位 (椰子水950ml x10件, ratio=12)
print("\n--- 订单 #1: 洪洪通 ---")
# 椰子水950ml 属于 shipper HZ2023101200002
items1 = [{"product_name": "椰子水950ml", "spec": "950ml*12瓶/件", "unit": "件", "quantity": 10, "seq": 1}]
results1, unmatch1 = map_sku_batch("HZ2023101200002", items1, DB_CONFIG)
for r in results1:
    print(f"  {r['sku_name']:20s} → {r['sku_code']:20s} type={r.get('unit_type',''):4s} qty={r.get('quantity',0)}")
    sku_ok = r["sku_code"] == "SK231013000200"
    type_ok = r.get("unit_type","") == "大单位"
    print(f"  SKU: {'✅' if sku_ok else '❌'} (GT=SK231013000200)  type: {'✅' if type_ok else '❌'} (GT=大单位)")
if unmatch1:
    for u in unmatch1:
        print(f"  ❌ 未匹配: {u['product_name']}")

# 订单 #9: 天津仓 2店11项
print("\n--- 订单 #9: 天津仓 (owner=HZ2024061300001) ---")
items9 = [
    # Store 1: 7 items (unit=件, GT=大单位 for all)
    {"product_name": "潮迹潮汕牛肉丸", "spec": "", "unit": "件", "quantity": 2, "seq": 1},
    {"product_name": "深岩静腌西冷牛排", "spec": "", "unit": "件", "quantity": 1, "seq": 2},
    {"product_name": "深岩静腌战斧牛排", "spec": "", "unit": "件", "quantity": 1, "seq": 3},
    {"product_name": "深岩静腌眼肉牛排(6袋)", "spec": "", "unit": "件", "quantity": 1, "seq": 4},
    {"product_name": "深岩静腌上脑牛排(6袋)", "spec": "", "unit": "件", "quantity": 1, "seq": 5},
    {"product_name": "艾熙雅韩式烤肠", "spec": "", "unit": "件", "quantity": 1, "seq": 6},
    {"product_name": "浩然猪大肠", "spec": "", "unit": "件", "quantity": 1, "seq": 7},
    # Store 2: 4 items
    {"product_name": "浩然奥尔良翅中（10袋）", "spec": "", "unit": "件", "quantity": 2, "seq": 8},
    {"product_name": "浩然奥尔良翅根（10袋）", "spec": "", "unit": "件", "quantity": 2, "seq": 9},
    {"product_name": "众享汇调味法式羊排", "spec": "", "unit": "件", "quantity": 1, "seq": 10},
    {"product_name": "浩然奥尔良鸡排", "spec": "", "unit": "件", "quantity": 2, "seq": 11},
]

results9, unmatch9 = map_sku_batch("HZ2024061300001", items9, DB_CONFIG)

gt_all = [
    ("SK241228000106", "大单位"), ("SK250820000194", "大单位"), ("SK250825000034", "大单位"),
    ("SK250908000961", "大单位"), ("SK250908000963", "大单位"), ("SK251219000076", "大单位"),
    ("SK260523001524", "大单位"),
    ("SK241225000055", "小单位"), ("SK241204000243", "小单位"),
    ("SK250923000371", "大单位"), ("SK240922000037", "大单位"),
]

sku_ok_count = 0
type_ok_count = 0
total = len(results9)

for i, r in enumerate(results9):
    gt_sku, gt_type = gt_all[i] if i < len(gt_all) else ("?", "?")
    sku_ok = r["sku_code"] == gt_sku
    type_ok = r.get("unit_type","") == gt_type
    if sku_ok: sku_ok_count += 1
    if type_ok: type_ok_count += 1
    store = "S1" if i < 7 else "S2"
    print(f"  {'✅' if sku_ok else '❌'}{'✅' if type_ok else '❌'} [{store}] {r['sku_name'][:25]:25s} → {r['sku_code']:20s} type={r.get('unit_type',''):4s} qty={r.get('quantity',0)} | GT={gt_sku} {gt_type}")

if unmatch9:
    print(f"\n  未匹配: {[u['product_name'] for u in unmatch9]}")

print(f"\n  SKU匹配: {sku_ok_count}/{total}")
print(f"  unit_type匹配: {type_ok_count}/{total}")

print()
print("=" * 60)
print("总结")
print("=" * 60)
