#!/usr/bin/env python3
"""
Accuracy audit for order-to-Huading mapping.

Metrics:
- Store accuracy: top matched store_code vs B-set ground truth.
- Owner accuracy: matched owner_code vs B-set ground truth.
- Warehouse accuracy: matched warehouse_code vs expected warehouse_code from DB.
- SKU accuracy: mapped sku_code vs A/D ground truth.
- Unit accuracy: mapped unit_type vs A/D ground truth.

This script intentionally separates "coverage" from "accuracy" so unresolved
store owners do not silently pollute SKU accuracy.
"""
import json
import os
import sys
from collections import defaultdict
from pathlib import Path


WORKSPACE = Path("/Users/jinqianfei/openclaw-workspaces/ai-order")
SKILL_DIR = WORKSPACE / "skills" / "skill_order_to_huading_template"
TEST_DATA = WORKSPACE / "docs" / "test_data"

sys.path.insert(0, str(SKILL_DIR))
sys.path.insert(0, str(WORKSPACE))


def load_env():
    env_path = WORKSPACE / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def db_config():
    return {
        "host": os.environ.get("DB_HOST"),
        "port": int(os.environ.get("DB_PORT", "5432")),
        "database": os.environ.get("DB_NAME", "neo"),
        "user": os.environ.get("DB_USER", "agenthub"),
        "password": os.environ.get("DB_PASSWORD", ""),
    }


def pct(hit, total):
    return (hit / total * 100.0) if total else 0.0


def top_store_result(result):
    if not result:
        return None
    candidates = result.get("candidates") or []
    if candidates:
        return candidates[0]
    if result.get("matched_store"):
        return result["matched_store"]
    return result


def load_db_reference(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT store_code, store_name, owner_code, owner_name, phone,
               address, contact_person, warehouse
        FROM store_list
    """)
    stores = {}
    store_by_name = {}
    for row in cur.fetchall():
        rec = {
            "store_code": row[0] or "",
            "store_name": row[1] or "",
            "owner_code": row[2] or "",
            "owner_name": row[3] or "",
            "phone": row[4] or "",
            "address": row[5] or "",
            "contact_person": row[6] or "",
            "warehouse_name": row[7] or "",
        }
        stores[rec["store_code"]] = rec
        store_by_name.setdefault(rec["store_name"], rec)

    cur.execute("SELECT warehouse_name, warehouse_code FROM warehouse_code_mapping")
    wh_map = {r[0] or "": r[1] or "" for r in cur.fetchall()}
    cur.close()
    return stores, store_by_name, wh_map


def audit_stores(db_cfg, stores_by_code, warehouse_map):
    from tools._store_matcher import match_store

    data = json.loads((TEST_DATA / "test_set_B_new_customer.json").read_text())
    rows = []
    totals = defaultdict(int)

    for case in data:
        expected_store = stores_by_code.get(case["store_code"], {})
        expected_warehouse_code = warehouse_map.get(expected_store.get("warehouse_name", ""), "")
        result = match_store(
            store_name=case.get("store_name", ""),
            db_config=db_cfg,
            phone=case.get("phone", ""),
            address=case.get("address", ""),
            contact_person=case.get("contact_person", ""),
        )
        top = top_store_result(result) or {}
        row = {
            "input": case.get("store_name", ""),
            "expected_store_code": case.get("store_code", ""),
            "got_store_code": top.get("store_code", ""),
            "expected_owner_code": case.get("owner_code", ""),
            "got_owner_code": top.get("owner_code", ""),
            "expected_warehouse_code": expected_warehouse_code,
            "got_warehouse_code": top.get("warehouse_code", ""),
            "match_type": top.get("match_type", result.get("match_type", "") if result else ""),
            "match_method": top.get("match_method", result.get("match_method", "") if result else ""),
        }
        row["store_hit"] = row["got_store_code"] == row["expected_store_code"]
        row["owner_hit"] = row["got_owner_code"] == row["expected_owner_code"]
        row["warehouse_hit"] = (
            bool(row["expected_warehouse_code"])
            and row["got_warehouse_code"] == row["expected_warehouse_code"]
        )
        rows.append(row)
        totals["total"] += 1
        totals["store_hit"] += int(row["store_hit"])
        totals["owner_hit"] += int(row["owner_hit"])
        totals["warehouse_total"] += int(bool(row["expected_warehouse_code"]))
        totals["warehouse_hit"] += int(row["warehouse_hit"])

    return totals, rows


def resolve_owner_for_store(store_name, store_by_name):
    if store_name in store_by_name:
        return store_by_name[store_name]["owner_code"], "exact"
    for name, rec in store_by_name.items():
        if store_name and (store_name in name or name in store_name):
            return rec["owner_code"], "contains"
    return "", "unresolved"


def audit_sku(db_cfg, store_by_name):
    from tools._sku_mapper import map_sku_batch

    rows = []
    totals = defaultdict(int)

    # A: historical orders. Use only rows that have explicit SKU GT.
    a_orders = json.loads((TEST_DATA / "test_set_A_history回流.json").read_text())
    for order in a_orders:
        source = order.get("source", "")
        gt = order.get("ground_truth", {})
        seq = 0
        for store_name, store_data in (order.get("stores") or {}).items():
            owner_code, owner_source = resolve_owner_for_store(store_name, store_by_name)
            for item in store_data.get("items", []):
                seq += 1
                gt_list = gt.get(str(seq), [])
                if not gt_list or not gt_list[0].get("sku"):
                    totals["sku_skipped_no_gt"] += 1
                    continue
                if not owner_code:
                    totals["sku_skipped_no_owner"] += 1
                    rows.append({
                        "set": "A",
                        "source": source,
                        "product_name": item.get("name", ""),
                        "expected_sku": gt_list[0].get("sku", ""),
                        "got_sku": "",
                        "expected_unit_type": gt_list[0].get("unit_type", ""),
                        "got_unit_type": "",
                        "sku_hit": False,
                        "unit_hit": False,
                        "status": "skipped_no_owner",
                    })
                    continue
                audit_one_sku(
                    rows, totals, map_sku_batch, db_cfg, "A", source, owner_code,
                    {
                        "product_name": item.get("name") or item.get("product_name", ""),
                        "spec": item.get("spec", ""),
                        "unit": item.get("unit", "件"),
                        "quantity": item.get("qty") or item.get("quantity", 1),
                        "seq": seq,
                    },
                    gt_list[0].get("sku", ""),
                    gt_list[0].get("unit_type", ""),
                    owner_source,
                )

    # D: blind SKU tests. Each case carries shipper_id and expected SKU.
    d_cases = json.loads((TEST_DATA / "test_set_D_blind_test.json").read_text())
    for case in d_cases:
        expected_sku = case.get("expected_sku", "")
        if not expected_sku:
            totals["sku_skipped_no_gt"] += 1
            continue
        audit_one_sku(
            rows, totals, map_sku_batch, db_cfg, "D", case.get("item_id", ""),
            case.get("shipper_id", ""),
            {
                "product_name": case.get("original_name", ""),
                "spec": case.get("spec", ""),
                "unit": case.get("unit", "件"),
                "quantity": 1,
                "seq": case.get("item_id", ""),
            },
            expected_sku,
            case.get("expected_unit_type", ""),
            "shipper_id",
        )

    return totals, rows


def audit_one_sku(rows, totals, map_sku_batch, db_cfg, set_name, source,
                  owner_code, item, expected_sku, expected_unit_type, owner_source):
    totals["sku_total"] += 1
    try:
        results, unmatched = map_sku_batch(owner_code, [item], db_cfg)
    except Exception as exc:
        totals["sku_exception"] += 1
        rows.append({
            "set": set_name,
            "source": source,
            "product_name": item["product_name"],
            "expected_sku": expected_sku,
            "got_sku": "",
            "expected_unit_type": expected_unit_type,
            "got_unit_type": "",
            "sku_hit": False,
            "unit_hit": False,
            "status": f"exception: {exc}",
        })
        return

    r = results[0] if results else {}
    got_sku = r.get("sku_code", "")
    got_unit_type = r.get("unit_type", "")
    sku_hit = got_sku == expected_sku
    unit_hit = got_unit_type == expected_unit_type if expected_unit_type else False
    totals["sku_hit"] += int(sku_hit)
    totals["unit_total"] += int(bool(expected_unit_type))
    totals["unit_hit"] += int(unit_hit)
    totals["unmatched"] += int(not results)
    totals["need_confirm"] += int(bool(r.get("need_confirm") or r.get("candidates")))

    rows.append({
        "set": set_name,
        "source": source,
        "owner_code": owner_code,
        "owner_source": owner_source,
        "product_name": item["product_name"],
        "unit": item.get("unit", ""),
        "expected_sku": expected_sku,
        "got_sku": got_sku or "UNMATCHED",
        "expected_unit_type": expected_unit_type,
        "got_unit_type": got_unit_type,
        "sku_hit": sku_hit,
        "unit_hit": unit_hit,
        "need_confirm": bool(r.get("need_confirm") or r.get("candidates")),
        "confidence": r.get("confidence", 0),
        "match_method": r.get("match_method", ""),
        "status": "matched" if results else "unmatched",
    })


def print_report(store_totals, store_rows, sku_totals, sku_rows):
    print("\n=== Store / Owner / Warehouse Accuracy (B set) ===")
    print(f"cases: {store_totals['total']}")
    print(f"store_code:     {store_totals['store_hit']}/{store_totals['total']} = {pct(store_totals['store_hit'], store_totals['total']):.1f}%")
    print(f"owner_code:     {store_totals['owner_hit']}/{store_totals['total']} = {pct(store_totals['owner_hit'], store_totals['total']):.1f}%")
    print(f"warehouse_code: {store_totals['warehouse_hit']}/{store_totals['warehouse_total']} = {pct(store_totals['warehouse_hit'], store_totals['warehouse_total']):.1f}%")

    store_fails = [r for r in store_rows if not (r["store_hit"] and r["owner_hit"] and (r["warehouse_hit"] or not r["expected_warehouse_code"]))]
    if store_fails:
        print("\nStore failures:")
        for r in store_fails:
            print(f"- {r['input']}: store {r['got_store_code']} vs {r['expected_store_code']}; "
                  f"owner {r['got_owner_code']} vs {r['expected_owner_code']}; "
                  f"wh {r['got_warehouse_code']} vs {r['expected_warehouse_code']} ({r['match_method']})")

    print("\n=== SKU / Unit Accuracy (A + D, explicit GT only) ===")
    print(f"sku evaluable: {sku_totals['sku_total']}")
    print(f"sku_code:      {sku_totals['sku_hit']}/{sku_totals['sku_total']} = {pct(sku_totals['sku_hit'], sku_totals['sku_total']):.1f}%")
    print(f"unit_type:     {sku_totals['unit_hit']}/{sku_totals['unit_total']} = {pct(sku_totals['unit_hit'], sku_totals['unit_total']):.1f}%")
    print(f"need_confirm:  {sku_totals['need_confirm']}/{sku_totals['sku_total']} = {pct(sku_totals['need_confirm'], sku_totals['sku_total']):.1f}%")
    print(f"unmatched:     {sku_totals['unmatched']}/{sku_totals['sku_total']} = {pct(sku_totals['unmatched'], sku_totals['sku_total']):.1f}%")
    print(f"skipped no GT: {sku_totals['sku_skipped_no_gt']}")
    print(f"skipped no owner: {sku_totals['sku_skipped_no_owner']}")

    sku_fails = [r for r in sku_rows if r.get("status") != "skipped_no_owner" and not r.get("sku_hit")]
    if sku_fails:
        print("\nSKU failures:")
        for r in sku_fails[:80]:
            print(f"- [{r['set']}] {r['product_name']} ({r.get('unit','')}): "
                  f"{r['got_sku']} vs {r['expected_sku']}; "
                  f"unit {r['got_unit_type']} vs {r['expected_unit_type']}; "
                  f"conf={r.get('confidence', 0)}; {r.get('match_method', '')}")
        if len(sku_fails) > 80:
            print(f"... plus {len(sku_fails) - 80} more")


def main():
    load_env()
    cfg = db_config()
    import psycopg2
    conn = psycopg2.connect(**cfg)
    try:
        stores_by_code, store_by_name, warehouse_map = load_db_reference(conn)
        store_totals, store_rows = audit_stores(cfg, stores_by_code, warehouse_map)
        sku_totals, sku_rows = audit_sku(cfg, store_by_name)
        print_report(store_totals, store_rows, sku_totals, sku_rows)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
