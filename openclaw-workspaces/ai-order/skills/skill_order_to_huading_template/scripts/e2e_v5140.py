#!/usr/bin/env python3
"""
e2e_v5140.py — v5.14.0 端到端真实订单测试

自动跑完所有历史订单 (2 个真实 Excel + 59 个 JSON GT), 对比 v5.13.3 vs v5.14.0:
  1. 真实 Excel 订单: 走完整 execute() 流程 (自动模拟用户确认)
  2. JSON GT 订单: 直接调 map_sku_batch() 比对 SKU 准确率

输出:
  - 真实订单对比表 (v5.13.3 vs v5.14.0 选中 SKU / unit_type / candidates)
  - GT 准确率汇总 (4 个 test_set 各跑一遍, 总准确率)
  - 失败 case 详细列表
"""
import sys
import os
import json
import time
import subprocess
from pathlib import Path

def _detect_workspace():
    env_ws = os.environ.get("AI_ORDER_WORKSPACE")
    if env_ws and os.path.isdir(env_ws):
        return Path(env_ws)
    script_dir = Path(__file__).resolve().parent
    for parent in script_dir.parents:
        if (parent / "skills" / "skill_order_to_huading_template").is_dir() and (parent / ".env").exists():
            return parent
    for parent in script_dir.parents:
        if (parent / "skills").is_dir():
            return parent
    return Path.cwd()


WORKSPACE = _detect_workspace()
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


def step(msg: str):
    print(f"\n→ {msg}")


# =============== 1. 真实 Excel 端到端 ===============


def run_real_excel_e2e():
    """跑 2 个真实 Excel 订单, 对比 v5.14.0 表现"""
    banner("Part 1: 真实 Excel 端到端 (洪洪通 + 天津仓)")

    from skills.skill_order_to_huading_template import OrderToHuadingTemplate
    from db.connection import get_default_db_config

    db_config = get_default_db_config()
    skill = OrderToHuadingTemplate(
        db_config=db_config,
        output_dir=str(WORKSPACE / "test_output_v5140")
    )
    print(f"\nSkill version: {skill.VERSION}")

    results = {}
    for order_no, file_name, expected_items in [
        (1, "洪洪通_1店1项.xlsx", 1),
        (2, "天津仓_2店11项.xlsx", 11),
    ]:
        step(f"订单 #{order_no}: {file_name} (期望 {expected_items} 项)")
        order_file = WORKSPACE / "data" / "test_orders" / file_name
        if not order_file.exists():
            print(f"  ❌ 文件不存在: {order_file}")
            continue

        # Step A: 第 1 次 execute — 取门店候选
        result_1 = skill.execute(order_input=str(order_file))
        if not result_1.get("need_store_confirm"):
            print(f"  ⚠️ 没触发门店确认, 跳过 (success={result_1.get('success')})")
            results[order_no] = {"file": file_name, "result_1": result_1}
            continue

        # Step B: 自动选最佳门店 (0)
        candidates = result_1.get("candidates", [])
        chosen = candidates[0] if candidates else result_1.get("matched_store", {})
        print(f"  门店确认: {chosen.get('store_name')} (owner={chosen.get('owner_code')})")

        # Step C: 第 2 次 execute — 传 confirmed_store, 自动确认所有 SKU
        result_2 = skill.execute(
            order_input=str(order_file),
            confirmed_store=chosen,
            confirmed_sku=True  # 全部自动确认
        )

        if not result_2.get("success"):
            print(f"  ❌ execute 失败: {result_2.get('message')}")
            results[order_no] = {"file": file_name, "result_2": result_2}
            continue

        # Step D: 展示 SKU 映射明细
        review = result_2.get("review_data", {})
        mapping_table = review.get("mapping_table", [])
        print(f"\n  门店数: {result_2.get('store_count')}")
        print(f"  商品数: {result_2.get('item_count')}")
        print(f"  匹配数: {result_2.get('matched_count')}")
        print(f"  未匹配: {result_2.get('unmatched_count')}")

        print(f"\n  SKU 映射对照表:")
        print(f"  {'#':<3} {'订单商品名':<20} {'单位':<5} {'数量':<5} {'SKU编码':<18} {'单位类型':<8} {'置信度':<6} {'candidates':<10}")
        print(f"  {'-'*100}")
        for row in mapping_table:
            cand_n = len(row.get("candidates", []) or [])
            print(f"  {row.get('seq', '?'):<3} "
                  f"{(row.get('customer_product_name', '') or '')[:18]:<20} "
                  f"{(row.get('customer_unit', '') or '')[:4]:<5} "
                  f"{row.get('customer_quantity', ''):<5} "
                  f"{(row.get('sku_code', '') or '')[:17]:<18} "
                  f"{(row.get('unit_type', '') or '')[:7]:<8} "
                  f"{row.get('confidence', 0):.2f}  "
                  f"{cand_n}")

        results[order_no] = {
            "file": file_name,
            "store_name": chosen.get("store_name"),
            "owner_code": chosen.get("owner_code"),
            "store_count": result_2.get("store_count"),
            "item_count": result_2.get("item_count"),
            "matched_count": result_2.get("matched_count"),
            "unmatched_count": result_2.get("unmatched_count"),
            "mapping_table": mapping_table,
            "output_file": result_2.get("output_file"),
        }

    return results


# =============== 2. JSON GT 准确率比对 ===============


def run_gt_comparison():
    """跑 59 个 JSON GT 订单, 比对 v5.14.0 SKU 匹配准确率"""
    banner("Part 2: JSON GT 准确率比对 (4 个 test_set, 59 个订单)")

    import importlib
    import tools._sku_mapper
    importlib.reload(tools._sku_mapper)
    from tools._sku_mapper import map_sku_batch

    db_config = {
        "host": os.environ.get("DB_HOST", "agenthub-db.cjys0msc4x8s.ap-southeast-1.rds.amazonaws.com"),
        "port": int(os.environ.get("DB_PORT", "5432")),
        "database": os.environ.get("DB_NAME", "neo"),
        "user": os.environ.get("DB_USER", "agenthub"),
        "password": os.environ.get("DB_PASSWORD", ""),
    }

    # 货主ID → store_list 表里的 owner_code 映射 (取第一个 store_name 反查)
    summary = {
        "A_history回流": {"total": 0, "hit_sku": 0, "hit_unit_type": 0, "cases": []},
        "B_new_customer": {"total": 0, "hit_sku": 0, "hit_unit_type": 0, "cases": []},
        "C_boundary_cases": {"total": 0, "hit_sku": 0, "hit_unit_type": 0, "cases": []},
        "D_blind_test": {"total": 0, "hit_sku": 0, "hit_unit_type": 0, "cases": []},
    }

    for set_name in summary.keys():
        step(f"Test set: {set_name}")
        file_path = WORKSPACE / "docs" / "test_data" / f"test_set_{set_name[0]}_{set_name.split('_', 1)[1]}.json"
        if not file_path.exists():
            print(f"  ❌ 文件不存在: {file_path}")
            continue

        with open(file_path) as f:
            orders = json.load(f)

        # 先扫描所有 owner_code (从 store_name → owner_code 映射表反查)
        # 由于没有自动反查, 用 store_name 在 store_list 表里查 owner_code
        import psycopg2
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()

        for order in orders:
            short_name = order.get("short_name", "")
            source = order.get("source", "")
            stores = order.get("stores", {})
            gt = order.get("ground_truth", {})

            if not stores or not gt:
                continue

            # 拿第一个门店名查 owner_code
            first_store_name = list(stores.keys())[0]
            cur.execute(
                "SELECT owner_code FROM store_list WHERE store_name = %s LIMIT 1",
                (first_store_name,)
            )
            row = cur.fetchone()
            if not row:
                # 试模糊查询
                cur.execute(
                    "SELECT owner_code FROM store_list WHERE store_name LIKE %s LIMIT 1",
                    (f"%{first_store_name[:10]}%",)
                )
                row = cur.fetchone()
            if not row:
                print(f"  ⚠️ 找不到门店 owner_code: {first_store_name[:30]}")
                continue
            owner_code = row[0]

            # 收集所有 items
            all_items = []
            for store_data in stores.values():
                for item in store_data.get("items", []):
                    all_items.append({
                        "product_name": item["name"],
                        "spec": item.get("spec", ""),
                        "unit": item.get("unit", "件"),
                        "quantity": item.get("qty", 1),
                        "seq": item.get("seq", len(all_items) + 1),
                    })
                # 单店订单第一个商品 seq 从 1 开始
                break  # 只取第一个店, GT 也只对第一个店

            # 跑 map_sku_batch
            try:
                results, unmatched = map_sku_batch(owner_code, all_items, db_config)
            except Exception as e:
                print(f"  ❌ {source[:30]}: {e}")
                continue

            # 比对 GT
            case = {
                "source": source,
                "short_name": short_name,
                "owner_code": owner_code,
                "items_count": len(all_items),
                "matched": 0,
                "unmatched": 0,
                "details": [],
            }

            for idx, item in enumerate(all_items, 1):
                gt_key = str(idx)
                gt_list = gt.get(gt_key, [])
                gt_sku = gt_list[0]["sku"] if gt_list else None
                gt_unit_type = gt_list[0]["unit_type"] if gt_list else None

                # 在 results 里找对应的 item
                r = None
                for rr in results:
                    if rr.get("product_name") == item["product_name"] and rr.get("quantity") == item["quantity"]:
                        r = rr
                        break
                if r is None and results:
                    r = results[idx - 1] if idx - 1 < len(results) else results[0]

                hit_sku = False
                hit_unit = False
                if r and r.get("matched"):
                    if r["sku_code"] == gt_sku:
                        hit_sku = True
                        case["matched"] += 1
                    else:
                        case["unmatched"] += 1
                    if r.get("unit_type") == gt_unit_type:
                        hit_unit = True
                else:
                    case["unmatched"] += 1

                case["details"].append({
                    "product_name": item["product_name"],
                    "unit": item["unit"],
                    "gt_sku": gt_sku,
                    "got_sku": r["sku_code"] if r else "UNMATCHED",
                    "gt_unit_type": gt_unit_type,
                    "got_unit_type": r.get("unit_type", "") if r else "",
                    "hit_sku": hit_sku,
                    "hit_unit_type": hit_unit,
                })

            case["hit_sku"] = case["matched"]
            case["hit_unit_type"] = sum(1 for d in case["details"] if d["hit_unit_type"])
            case["total"] = len(case["details"])
            case["accuracy_sku"] = case["matched"] / case["total"] if case["total"] else 0
            case["accuracy_unit_type"] = case["hit_unit_type"] / case["total"] if case["total"] else 0

            summary[set_name]["total"] += case["total"]
            summary[set_name]["hit_sku"] += case["matched"]
            summary[set_name]["hit_unit_type"] += case["hit_unit_type"]
            summary[set_name]["cases"].append(case)

        conn.close()

    return summary


# =============== 3. 输出报告 ===============


def print_report(real_results, gt_summary):
    banner("📊 v5.14.0 端到端测试报告")

    # 真实 Excel 部分
    print("\n【Part 1: 真实 Excel 端到端】")
    for order_no, r in real_results.items():
        if "result_2" in r and r.get("output_file"):
            print(f"  订单 #{order_no}: {r.get('file', '?')}")
            print(f"    门店: {r.get('store_name', '?')[:30]}")
            print(f"    商品: {r.get('item_count', '?')} | 匹配: {r.get('matched_count', '?')} | 未匹配: {r.get('unmatched_count', '?')}")
            print(f"    Excel: {r.get('output_file', '?')}")

    # GT 准确率
    print("\n【Part 2: JSON GT 准确率】")
    print(f"  {'Test Set':<25} {'商品数':<8} {'SKU 命中':<10} {'SKU准确率':<10} {'单位类型命中':<14} {'单位类型准确率':<10}")
    print(f"  {'-'*85}")

    total_items = 0
    total_sku_hit = 0
    total_unit_hit = 0
    for set_name, s in gt_summary.items():
        if s["total"] == 0:
            print(f"  {set_name:<25} {'(无数据)':<8}")
            continue
        sku_acc = s["hit_sku"] / s["total"] * 100
        unit_acc = s["hit_unit_type"] / s["total"] * 100
        print(f"  {set_name:<25} {s['total']:<8} {s['hit_sku']:<10} {sku_acc:>6.1f}%     {s['hit_unit_type']:<14} {unit_acc:>6.1f}%")
        total_items += s["total"]
        total_sku_hit += s["hit_sku"]
        total_unit_hit += s["hit_unit_type"]

    print(f"  {'-'*85}")
    if total_items:
        print(f"  {'总计':<25} {total_items:<8} {total_sku_hit:<10} {total_sku_hit/total_items*100:>6.1f}%     {total_unit_hit:<14} {total_unit_hit/total_items*100:>6.1f}%")

    # 失败明细
    print(f"\n【失败 case 明细 (sku 不命中)】")
    fail_count = 0
    for set_name, s in gt_summary.items():
        for case in s["cases"]:
            for d in case["details"]:
                if not d["hit_sku"] and d["got_sku"] != "UNMATCHED":
                    print(f"  [{set_name[0]}] {case['source'][:20]:<20} | "
                          f"{d['product_name'][:18]:<18} unit={d['unit']:<4} | "
                          f"GT={d['gt_sku']} | got={d['got_sku']} ({d['got_unit_type']})")
                    fail_count += 1
                    if fail_count > 30:
                        print(f"  ... (省略更多)")
                        break
            if fail_count > 30:
                break
        if fail_count > 30:
            break

    if fail_count == 0:
        print(f"  ✅ 全部命中!")

    print(f"\n【未匹配 case (got=UNMATCHED)】")
    um_count = 0
    for set_name, s in gt_summary.items():
        for case in s["cases"]:
            for d in case["details"]:
                if d["got_sku"] == "UNMATCHED":
                    print(f"  [{set_name[0]}] {case['source'][:20]:<20} | "
                          f"{d['product_name'][:18]:<18} unit={d['unit']:<4} | "
                          f"GT={d['gt_sku']}")
                    um_count += 1
                    if um_count > 20:
                        break
            if um_count > 20:
                break
        if um_count > 20:
            break
    if um_count == 0:
        print(f"  ✅ 无未匹配!")


# =============== 主函数 ===============


def main():
    print("=" * 70)
    print("  v5.14.0 端到端真实订单测试")
    print(f"  时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # Part 1
    real_results = run_real_excel_e2e()

    # Part 2
    gt_summary = run_gt_comparison()

    # 报告
    print_report(real_results, gt_summary)

    print("\n" + "=" * 70)
    print("  测试完成")
    print("=" * 70)


if __name__ == "__main__":
    main()