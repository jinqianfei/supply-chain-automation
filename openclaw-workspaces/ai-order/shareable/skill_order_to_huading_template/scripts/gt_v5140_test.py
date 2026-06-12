#!/usr/bin/env python3
"""
gt_v5140_test.py — 59 个 JSON GT 订单的 v5.14.0 准确率测试

跳过 execute() 完整流程, 直接调 map_sku_batch() 比对 GT

输出:
  - 4 个 test_set 的准确率表
  - 总准确率
  - 失败 case 明细
"""
import sys
import os
import json
import time
from pathlib import Path

WORKSPACE = Path("/Users/jinqianfei/openclaw-workspaces/ai-order")
SKILL_DIR = WORKSPACE / "skills" / "skill_order_to_huading_template"
sys.path.insert(0, str(SKILL_DIR))
sys.path.insert(0, str(WORKSPACE))
os.chdir(WORKSPACE)

# 加载 .env
env_path = WORKSPACE / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def banner(msg: str):
    print("\n" + "=" * 70)
    print(f"  {msg}")
    print("=" * 70)


def main():
    banner("v5.14.0 GT 准确率测试 - 59 个历史订单")

    import psycopg2
    db_config = {
        "host": os.environ.get("DB_HOST"),
        "port": int(os.environ.get("DB_PORT", "5432")),
        "database": os.environ.get("DB_NAME", "neo"),
        "user": os.environ.get("DB_USER", "agenthub"),
        "password": os.environ.get("DB_PASSWORD", ""),
    }

    import importlib
    import tools._sku_mapper
    importlib.reload(tools._sku_mapper)
    from tools._sku_mapper import map_sku_batch

    test_sets = [
        ("A_history回流", "test_set_A_history回流.json"),
        ("B_new_customer", "test_set_B_new_customer.json"),
        ("C_boundary_cases", "test_set_C_boundary_cases.json"),
        ("D_blind_test", "test_set_D_blind_test.json"),
    ]

    # 预加载所有门店的 owner_code 缓存
    conn = psycopg2.connect(**db_config)
    cur = conn.cursor()
    cur.execute("SELECT store_name, owner_code FROM store_list")
    store_owner_map = {r[0]: r[1] for r in cur.fetchall()}
    print(f"\n已加载 {len(store_owner_map)} 条门店 owner_code 映射")

    # 总计
    grand_total = 0
    grand_sku_hit = 0
    grand_unit_hit = 0
    grand_candidates_count = 0
    grand_unmatched = 0
    all_fails = []
    all_unmatched = []

    print(f"\n{'='*70}\n  准确率表\n{'='*70}")
    print(f"  {'Test Set':<20} {'商品':<6} {'SKU 命中':<10} {'SKU%':<7} {'单位类型%':<10} {'需确认':<8} {'未匹配':<8}")
    print(f"  {'-'*70}")

    for set_name, file_name in test_sets:
        file_path = WORKSPACE / "docs" / "test_data" / file_name
        if not file_path.exists():
            print(f"  {set_name:<20} ❌ 文件不存在")
            continue

        with open(file_path) as f:
            orders = json.load(f)

        set_total = 0
        set_sku_hit = 0
        set_unit_hit = 0
        set_candidates = 0
        set_unmatched = 0

        for order in orders:
            short_name = order.get("short_name", "")
            source = order.get("source", order.get("store_name", ""))
            stores = order.get("stores", {})
            gt = order.get("ground_truth", {})

            # 收集所有门店的所有 items
            all_items = []
            store_idx = 0  # 用于对到 ground_truth 的 key
            store_keys = []  # 记录每个 store 的 seq 范围

            if stores:
                # 多门店结构 (A set)
                for store_name, store_data in stores.items():
                    owner_code = store_owner_map.get(store_name)
                    if not owner_code:
                        for k, v in store_owner_map.items():
                            if store_name[:8] in k or k[:8] in store_name:
                                owner_code = v
                                break
                    if not owner_code:
                        all_fails.append((set_name, source, store_name, "未找到 owner_code"))
                        continue
                    store_idx += 1
                    items_in_store = store_data.get("items", [])
                    seq_start = len(all_items) + 1
                    for item in items_in_store:
                        all_items.append({
                            "product_name": item.get("name") or item.get("product_name", ""),
                            "spec": item.get("spec", ""),
                            "unit": item.get("unit", "件"),
                            "quantity": item.get("qty") or item.get("quantity", 1),
                            "seq": len(all_items) + 1,
                            "owner_code": owner_code,
                            "store_idx": store_idx,
                        })
                    store_keys.append((store_idx, seq_start, len(all_items)))
            else:
                # 扁平结构 (B/C/D)
                owner_code = order.get("owner_code")
                first_store_name = order.get("store_name", "")
                if not owner_code:
                    all_fails.append((set_name, source, first_store_name, "未找到 owner_code"))
                    continue
                items = order.get("items", [])
                for item in items:
                    all_items.append({
                        "product_name": item.get("name") or item.get("product_name", ""),
                        "spec": item.get("spec", ""),
                        "unit": item.get("unit", "件"),
                        "quantity": item.get("qty") or item.get("quantity", 1),
                        "seq": len(all_items) + 1,
                        "owner_code": owner_code,
                        "store_idx": 1,
                    })
                store_keys.append((1, 1, len(all_items)))

            if not all_items or not gt:
                continue

            # 按 store_idx 分组跑
            for store_idx, seq_start, seq_end in store_keys:
                # 该门店的 items
                store_items = [it for it in all_items[seq_start-1:seq_end] if it.get("store_idx") == store_idx]
                if not store_items:
                    continue
                store_owner = store_items[0]["owner_code"]

                # 跑 v5.14.0
                try:
                    # map_sku_batch 不需要 store_idx 字段
                    clean_items = [{k: v for k, v in it.items() if k not in ("owner_code", "store_idx")} for it in store_items]
                    results, unmatched = map_sku_batch(store_owner, clean_items, db_config)
                except Exception as e:
                    all_fails.append((set_name, source, f"store#{store_idx}", "EXCEPTION", str(e)))
                    continue

                # 比对该门店的 GT
                for local_idx, item in enumerate(store_items, 1):
                    # global_seq = 该门店在该订单里的全局 seq
                    global_seq = seq_start + local_idx - 1
                    gt_key = str(global_seq)
                    gt_list = gt.get(gt_key, [])
                    gt_sku = gt_list[0]["sku"] if gt_list else None
                    gt_unit_type = gt_list[0]["unit_type"] if gt_list else None

                    r = results[local_idx - 1] if local_idx - 1 < len(results) else None

                    set_total += 1
                    if r is None or not r.get("matched"):
                        set_unmatched += 1
                        all_unmatched.append((set_name, source, item["product_name"], gt_sku, item["unit"]))
                        continue

                    if r["sku_code"] == gt_sku:
                        set_sku_hit += 1
                    else:
                        all_fails.append((set_name, source, item["product_name"], item["unit"], gt_sku, r["sku_code"], r["unit_type"], r.get("match_method", "")[:30]))

                    if r.get("unit_type") == gt_unit_type:
                        set_unit_hit += 1

                    if r.get("candidates"):
                        set_candidates += 1

        sku_acc = set_sku_hit / set_total * 100 if set_total else 0
        unit_acc = set_unit_hit / set_total * 100 if set_total else 0
        print(f"  {set_name:<20} {set_total:<6} {set_sku_hit:<10} {sku_acc:>5.1f}%  {unit_acc:>7.1f}%    {set_candidates:<8} {set_unmatched:<8}")

        grand_total += set_total
        grand_sku_hit += set_sku_hit
        grand_unit_hit += set_unit_hit
        grand_candidates_count += set_candidates
        grand_unmatched += set_unmatched

    print(f"  {'-'*70}")
    sku_acc = grand_sku_hit / grand_total * 100 if grand_total else 0
    unit_acc = grand_unit_hit / grand_total * 100 if grand_total else 0
    print(f"  {'总计':<20} {grand_total:<6} {grand_sku_hit:<10} {sku_acc:>5.1f}%  {unit_acc:>7.1f}%    {grand_candidates_count:<8} {grand_unmatched:<8}")

    # 失败明细
    print(f"\n{'='*70}\n  SKU 不命中明细 ({len(all_fails)} 个)\n{'='*70}")
    print(f"  {'Set':<3} {'源':<20} {'商品':<18} {'单位':<5} {'GT SKU':<18} {'got SKU':<18} {'got type':<8} {'method':<25}")
    print(f"  {'-'*120}")
    for f in all_fails[:50]:
        if len(f) == 4:
            print(f"  {f[0][0]:<3} {f[1][:18]:<20} {f[2][:16]:<18} {'-':<5} 错误: {f[3]}")
        else:
            set_short, source, prod, unit, gt, got, got_type, method = f
            gt_s = gt or '-'
            got_s = got or '-'
            got_t = got_type or '-'
            print(f"  {set_short[0]:<3} {source[:18]:<20} {prod[:16]:<18} {unit:<5} {gt_s:<18} {got_s:<18} {got_t:<8} {method:<25}")
    if len(all_fails) > 50:
        print(f"  ... 还有 {len(all_fails)-50} 个")

    # 未匹配明细
    print(f"\n{'='*70}\n  未匹配明细 ({len(all_unmatched)} 个)\n{'='*70}")
    print(f"  {'Set':<3} {'源':<20} {'商品':<18} {'单位':<5} {'GT SKU':<18}")
    print(f"  {'-'*70}")
    for f in all_unmatched[:30]:
        set_short, source, prod, gt, unit = f
        print(f"  {set_short[0]:<3} {source[:18]:<20} {prod[:16]:<18} {unit:<5} {gt if gt else '-':<18}")
    if len(all_unmatched) > 30:
        print(f"  ... 还有 {len(all_unmatched)-30} 个")

    print(f"\n{'='*70}\n  总结\n{'='*70}")
    print(f"  总商品数: {grand_total}")
    print(f"  SKU 命中: {grand_sku_hit} ({sku_acc:.1f}%)")
    print(f"  单位类型命中: {grand_unit_hit} ({unit_acc:.1f}%)")
    print(f"  candidates (需用户选): {grand_candidates_count} ({grand_candidates_count/grand_total*100:.1f}%)")
    print(f"  未匹配: {grand_unmatched} ({grand_unmatched/grand_total*100:.1f}%)")
    print(f"  SKU 不命中: {len(all_fails)} ({len(all_fails)/grand_total*100:.1f}%)")

    conn.close()


if __name__ == "__main__":
    main()