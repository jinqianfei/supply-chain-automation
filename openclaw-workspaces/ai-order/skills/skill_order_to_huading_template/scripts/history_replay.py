#!/usr/bin/env python3
"""
history_replay.py — 历史订单回放脚本

从 order_feedback 表取历史订单（source_file 不为空），
用当前版本 Skill 重新跑 execute()，对比新旧匹配结果（sku_code 是否一致），
输出 Markdown 报告到 /tmp/history_replay_YYYYMMDD.md

用法:
    python3 skills/skill_order_to_huading_template/scripts/history_replay.py

报告包含：总订单数、一致数、不一致数、准确率、不一致明细
"""
import sys
import os
import time
import datetime
import traceback
from pathlib import Path

# ── 路径 & .env ──
WORKSPACE = Path("/Users/jinqianfei/openclaw-workspaces/ai-order")
SKILL_DIR = WORKSPACE / "skills" / "skill_order_to_huading_template"
sys.path.insert(0, str(SKILL_DIR))
sys.path.insert(0, str(WORKSPACE))
os.chdir(WORKSPACE)

env_path = WORKSPACE / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

# ── 依赖 ──
import psycopg2
import openpyxl


def get_db_config():
    return {
        "host": os.environ.get("DB_HOST"),
        "port": int(os.environ.get("DB_PORT", "5432")),
        "database": os.environ.get("DB_NAME", "neo"),
        "user": os.environ.get("DB_USER", "agenthub"),
        "password": os.environ.get("DB_PASSWORD", ""),
    }


def fetch_historical_orders(db_config):
    """从 order_feedback 取所有有 source_file 的记录"""
    conn = psycopg2.connect(**db_config)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, source_file, output_file, owner_code,
               sku_count, matched_sku_count, sku_match_rate,
               skill_version, order_date, session_id,
               jsonb_array_length(COALESCE(corrections, '[]'::jsonb)) as corr_count,
               user_confirmed, user_modified
        FROM order_feedback
        WHERE source_file IS NOT NULL AND source_file != ''
        ORDER BY id
    """)
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def read_output_sku_codes(output_file_path):
    """读取华鼎出库单 Excel，提取 (序号, 门店编号, SKU编号, 单位类型, 出库数量)"""
    if not output_file_path or not os.path.exists(output_file_path):
        return None

    try:
        wb = openpyxl.load_workbook(output_file_path, read_only=True)
        ws = wb.active
        rows = []
        for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=1):
            if row[0] is None:  # 空行
                continue
            rows.append({
                "seq": row[0],
                "store_code": row[1],
                "sku_code": row[5],      # Col 6: 商品SKU编号
                "unit_type": row[7],     # Col 8: 单位类型
                "quantity": row[8],      # Col 9: 出库数量
            })
        wb.close()
        return rows
    except Exception as e:
        print(f"    ⚠️  读取输出文件失败: {e}")
        return None


def run_replay_for_order(skill, order, db_config):
    """
    对单个历史订单执行回放：
    1. 第一次 execute() 获取门店匹配结果 + order_data_cache
    2. 自动确认门店，第二次 execute() 获取最终结果
    3. 对比新旧 SKU 映射
    """
    source_file = order["source_file"]
    old_output_file = order["output_file"]
    feedback_id = order["id"]

    result = {
        "feedback_id": feedback_id,
        "source_file": source_file,
        "old_output_file": old_output_file,
        "old_version": order["skill_version"],
        "order_date": str(order["order_date"]),
        "owner_code": order["owner_code"],
        "old_sku_count": order["sku_count"],
        "old_matched": order["matched_sku_count"],
        "old_match_rate": order["sku_match_rate"],
        "status": "pending",
        "error": None,
        "new_output_file": None,
        "new_sku_count": 0,
        "new_matched": 0,
        "comparison": [],  # [{seq, old_sku, new_sku, match}]
        "consistent": 0,
        "inconsistent": 0,
        "total_compared": 0,
    }

    # 检查源文件是否存在
    if not os.path.exists(source_file):
        result["status"] = "skipped"
        result["error"] = f"源文件不存在: {source_file}"
        return result

    # ── Pass 1: 获取门店匹配 + cache ──
    try:
        t0 = time.time()
        r1 = skill.execute(order_input=source_file)
        elapsed_p1 = time.time() - t0
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"Pass 1 异常: {e}"
        return result

    # 如果直接成功（无需确认，罕见情况）
    if r1.get("success"):
        result["new_output_file"] = r1.get("output_file")
        result["new_sku_count"] = r1.get("item_count", 0)
        result["new_matched"] = r1.get("item_count", 0) - len(r1.get("unmatched_items", []))
        # 对比
        _do_comparison(result, old_output_file, result["new_output_file"])
        return result

    # 需要门店确认
    if r1.get("need_store_confirm"):
        matched_store = r1.get("matched_store", {})
        pending_key = r1.get("pending_store_key", "")
        order_data_cache = r1.get("order_data_cache")
        confirmed_stores = r1.get("confirmed_stores", {})

        # 构建 confirmed_store
        if matched_store:
            confirmed_store = {
                "store_code": matched_store.get("store_code", ""),
                "store_name": matched_store.get("store_name", ""),
                "owner_code": matched_store.get("owner_code", ""),
                "owner_name": matched_store.get("owner_name", ""),
                "warehouse_name": matched_store.get("warehouse_name", ""),
                "warehouse_code": matched_store.get("warehouse_code", ""),
                "address": matched_store.get("address", ""),
                "contact_person": matched_store.get("contact_person", ""),
                "phone": matched_store.get("phone", ""),
                "similarity": matched_store.get("similarity", 1.0),
                "match_type": matched_store.get("match_type", ""),
                "match_method": matched_store.get("match_method", ""),
                "store_name_submitted": matched_store.get("store_name_submitted", ""),
                "_store_key": pending_key,
            }
        else:
            result["status"] = "error"
            result["error"] = "门店匹配返回无 matched_store"
            return result

        # ── Pass 2: 自动确认门店 + 自动确认 SKU ──
        try:
            t1 = time.time()
            r2 = skill.execute(
                order_input=source_file,
                confirmed_store=confirmed_store,
                confirmed_sku=True,
                order_data_cache=order_data_cache,
            )
            elapsed_p2 = time.time() - t1
        except Exception as e:
            result["status"] = "error"
            result["error"] = f"Pass 2 异常: {e}"
            return result

        # 如果 Pass 2 还需要门店确认（多门店场景，还有下一个门店待确认）
        # 循环处理所有门店
        max_iters = 20  # 安全上限
        iters = 0
        while r2.get("need_store_confirm") and iters < max_iters:
            iters += 1
            ms = r2.get("matched_store", {})
            pk = r2.get("pending_store_key", "")
            if not ms:
                break
            cs = r2.get("confirmed_stores", {})
            cs[pk] = {
                "store_code": ms.get("store_code", ""),
                "store_name": ms.get("store_name", ""),
                "owner_code": ms.get("owner_code", ""),
                "owner_name": ms.get("owner_name", ""),
                "warehouse_name": ms.get("warehouse_name", ""),
                "warehouse_code": ms.get("warehouse_code", ""),
                "address": ms.get("address", ""),
                "contact_person": ms.get("contact_person", ""),
                "phone": ms.get("phone", ""),
                "similarity": ms.get("similarity", 1.0),
                "match_type": ms.get("match_type", ""),
                "match_method": ms.get("match_method", ""),
                "store_name_submitted": ms.get("store_name_submitted", ""),
                "_store_key": pk,
            }
            try:
                r2 = skill.execute(
                    order_input=source_file,
                    confirmed_store={"confirmed_stores": cs},
                    confirmed_sku=True,
                    order_data_cache=r2.get("order_data_cache", order_data_cache),
                )
            except Exception as e:
                result["status"] = "error"
                result["error"] = f"多门店 Pass 异常 (iter {iters}): {e}"
                return result

        # 如果还需要 SKU 确认（need_sku_confirm），自动确认
        if r2.get("need_sku_confirm"):
            sku_mapping = r2.get("sku_mapping", [])
            confirmed_sku_dict = {}
            for item in sku_mapping:
                if item.get("matched") and item.get("sku_code"):
                    confirmed_sku_dict[str(item.get("seq", ""))] = {
                        "sku_code": item["sku_code"],
                        "sku_name": item.get("sku_name", ""),
                        "unit_type": item.get("unit_type", ""),
                        "quantity": item.get("quantity", 1),
                    }
            try:
                r2 = skill.execute(
                    order_input=source_file,
                    confirmed_store={"confirmed_stores": cs} if cs else confirmed_store,
                    confirmed_sku=confirmed_sku_dict if confirmed_sku_dict else True,
                    order_data_cache=r2.get("order_data_cache", order_data_cache),
                )
            except Exception as e:
                result["status"] = "error"
                result["error"] = f"SKU 确认 Pass 异常: {e}"
                return result

        if r2.get("success"):
            result["new_output_file"] = r2.get("output_file")
            result["new_sku_count"] = r2.get("item_count", 0)
            result["new_matched"] = r2.get("item_count", 0) - len(r2.get("unmatched_items", []))
            _do_comparison(result, old_output_file, result["new_output_file"])
        else:
            result["status"] = "failed"
            result["error"] = r2.get("message", "Pass 2 未成功")

    elif r1.get("need_ocr") or r1.get("need_pdf_ocr"):
        result["status"] = "skipped"
        result["error"] = "需要 OCR 识别，跳过回放"
    else:
        result["status"] = "error"
        result["error"] = f"未知返回状态: {list(r1.keys())}"

    return result


def _do_comparison(result, old_output_file, new_output_file):
    """对比新旧输出文件的 SKU 映射"""
    old_rows = read_output_sku_codes(old_output_file)
    new_rows = read_output_sku_codes(new_output_file)

    if old_rows is None:
        result["status"] = "no_old_output"
        result["error"] = f"旧输出文件不存在或无法读取: {old_output_file}"
        return

    if new_rows is None:
        result["status"] = "no_new_output"
        result["error"] = "新输出文件无法读取"
        return

    # 按序号对齐对比
    old_by_seq = {str(r["seq"]): r for r in old_rows}
    new_by_seq = {str(r["seq"]): r for r in new_rows}

    all_seqs = sorted(set(list(old_by_seq.keys()) + list(new_by_seq.keys())),
                      key=lambda x: int(x) if x.isdigit() else 0)

    consistent = 0
    inconsistent = 0
    comparisons = []

    for seq in all_seqs:
        old = old_by_seq.get(seq)
        new = new_by_seq.get(seq)

        old_sku = old["sku_code"] if old else None
        new_sku = new["sku_code"] if new else None

        match = (old_sku == new_sku) if (old_sku and new_sku) else None
        if match is True:
            consistent += 1
        elif match is False:
            inconsistent += 1

        comparisons.append({
            "seq": seq,
            "old_sku": old_sku,
            "new_sku": new_sku,
            "old_unit_type": old["unit_type"] if old else None,
            "new_unit_type": new["unit_type"] if new else None,
            "old_qty": old["quantity"] if old else None,
            "new_qty": new["quantity"] if new else None,
            "match": match,
        })

    result["comparison"] = comparisons
    result["consistent"] = consistent
    result["inconsistent"] = inconsistent
    result["total_compared"] = consistent + inconsistent
    result["status"] = "compared"


def generate_report(results, output_path):
    """生成 Markdown 报告"""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    total = len(results)
    compared = [r for r in results if r["status"] == "compared"]
    skipped = [r for r in results if r["status"] == "skipped"]
    errors = [r for r in results if r["status"] == "error"]
    failed = [r for r in results if r["status"] == "failed"]
    no_old = [r for r in results if r["status"] == "no_old_output"]
    no_new = [r for r in results if r["status"] == "no_new_output"]

    total_compared_items = sum(r["total_compared"] for r in compared)
    total_consistent = sum(r["consistent"] for r in compared)
    total_inconsistent = sum(r["inconsistent"] for r in compared)
    accuracy = (total_consistent / total_compared_items * 100) if total_compared_items > 0 else 0

    lines = []
    lines.append(f"# 历史订单回放报告")
    lines.append(f"")
    lines.append(f"**生成时间**: {now}")
    lines.append(f"")

    # ── 总览 ──
    lines.append(f"## 总览")
    lines.append(f"")
    lines.append(f"| 指标 | 数值 |")
    lines.append(f"|------|------|")
    lines.append(f"| 总订单数 | {total} |")
    lines.append(f"| 成功对比 | {len(compared)} |")
    lines.append(f"| 跳过 | {len(skipped)} |")
    lines.append(f"| 错误 | {len(errors)} |")
    lines.append(f"| 失败 | {len(failed)} |")
    lines.append(f"| 无旧输出 | {len(no_old)} |")
    lines.append(f"| 无新输出 | {len(no_new)} |")
    lines.append(f"")

    # ── SKU 准确率 ──
    lines.append(f"## SKU 映射对比")
    lines.append(f"")
    lines.append(f"| 指标 | 数值 |")
    lines.append(f"|------|------|")
    lines.append(f"| 对比商品总数 | {total_compared_items} |")
    lines.append(f"| SKU 一致 | {total_consistent} |")
    lines.append(f"| SKU 不一致 | {total_inconsistent} |")
    lines.append(f"| **准确率** | **{accuracy:.1f}%** |")
    lines.append(f"")

    # ── 各订单明细 ──
    lines.append(f"## 各订单明细")
    lines.append(f"")
    lines.append(f"| ID | 旧版本 | 订单日期 | 货主 | 旧SKU数 | 旧匹配率 | 状态 | 一致 | 不一致 | 新准确率 |")
    lines.append(f"|----|--------|----------|------|---------|----------|------|------|--------|----------|")

    for r in results:
        old_rate = f"{r['old_match_rate']*100:.0f}%" if r['old_match_rate'] is not None else "-"
        if r["status"] == "compared":
            new_acc = f"{r['consistent']/r['total_compared']*100:.0f}%" if r["total_compared"] > 0 else "-"
            lines.append(
                f"| {r['feedback_id']} | {r['old_version']} | {r['order_date']} | "
                f"{(r['owner_code'] or '')[:12]} | {r['old_sku_count']} | {old_rate} | "
                f"✅ | {r['consistent']} | {r['inconsistent']} | {new_acc} |"
            )
        else:
            lines.append(
                f"| {r['feedback_id']} | {r['old_version']} | {r['order_date']} | "
                f"{(r['owner_code'] or '')[:12]} | {r['old_sku_count']} | {old_rate} | "
                f"❌ {r['status']} | - | - | - |"
            )
    lines.append(f"")

    # ── 不一致明细 ──
    all_inconsistencies = []
    for r in compared:
        for c in r["comparison"]:
            if c["match"] is False:
                all_inconsistencies.append({**c, "feedback_id": r["feedback_id"],
                                             "source": os.path.basename(r["source_file"]),
                                             "old_version": r["old_version"]})

    if all_inconsistencies:
        lines.append(f"## 不一致明细 ({len(all_inconsistencies)} 个)")
        lines.append(f"")
        lines.append(f"| 订单ID | 源文件 | 序号 | 旧SKU | 新SKU | 旧单位类型 | 新单位类型 |")
        lines.append(f"|--------|--------|------|-------|-------|------------|------------|")
        for inc in all_inconsistencies:
            lines.append(
                f"| {inc['feedback_id']} | {inc['source'][:30]} | {inc['seq']} | "
                f"{inc['old_sku'] or '-'} | {inc['new_sku'] or '-'} | "
                f"{inc['old_unit_type'] or '-'} | {inc['new_unit_type'] or '-'} |"
            )
        lines.append(f"")

    # ── 跳过/错误明细 ──
    issues = skipped + errors + failed + no_old + no_new
    if issues:
        lines.append(f"## 跳过/错误明细 ({len(issues)} 个)")
        lines.append(f"")
        lines.append(f"| 订单ID | 状态 | 原因 |")
        lines.append(f"|--------|------|------|")
        for r in issues:
            lines.append(f"| {r['feedback_id']} | {r['status']} | {r['error'] or '-'} |")
        lines.append(f"")

    report = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    return report


def main():
    today = datetime.datetime.now().strftime("%Y%m%d")
    report_path = f"/tmp/history_replay_{today}.md"

    print("=" * 70)
    print(f"  历史订单回放 — {today}")
    print("=" * 70)

    db_config = get_db_config()
    orders = fetch_historical_orders(db_config)
    print(f"\n📋 找到 {len(orders)} 条历史订单记录")

    # 初始化 Skill
    from __init__ import OrderToHuadingTemplate
    skill = OrderToHuadingTemplate(db_config=db_config)
    print(f"✅ Skill 初始化完成")

    results = []
    for i, order in enumerate(orders):
        src = os.path.basename(order["source_file"])
        print(f"\n[{i+1}/{len(orders)}] 回放订单 #{order['id']} ({src[:40]}...)")

        if not os.path.exists(order["source_file"]):
            print(f"    ⏭️  源文件不存在，跳过")
            results.append({
                "feedback_id": order["id"],
                "source_file": order["source_file"],
                "old_output_file": order["output_file"],
                "old_version": order["skill_version"],
                "order_date": str(order["order_date"]),
                "owner_code": order["owner_code"],
                "old_sku_count": order["sku_count"],
                "old_matched": order["matched_sku_count"],
                "old_match_rate": order["sku_match_rate"],
                "status": "skipped",
                "error": f"源文件不存在",
                "new_output_file": None,
                "new_sku_count": 0,
                "new_matched": 0,
                "comparison": [],
                "consistent": 0,
                "inconsistent": 0,
                "total_compared": 0,
            })
            continue

        try:
            r = run_replay_for_order(skill, order, db_config)
            results.append(r)
            status_icon = "✅" if r["status"] == "compared" else "⚠️"
            print(f"    {status_icon} 状态: {r['status']}"
                  + (f" | 一致: {r['consistent']}, 不一致: {r['inconsistent']}"
                     if r["status"] == "compared" else f" | {r.get('error', '')[:60]}"))
        except Exception as e:
            print(f"    ❌ 异常: {e}")
            results.append({
                "feedback_id": order["id"],
                "source_file": order["source_file"],
                "old_output_file": order["output_file"],
                "old_version": order["skill_version"],
                "order_date": str(order["order_date"]),
                "owner_code": order["owner_code"],
                "old_sku_count": order["sku_count"],
                "old_matched": order["matched_sku_count"],
                "old_match_rate": order["sku_match_rate"],
                "status": "error",
                "error": str(e),
                "new_output_file": None,
                "new_sku_count": 0,
                "new_matched": 0,
                "comparison": [],
                "consistent": 0,
                "inconsistent": 0,
                "total_compared": 0,
            })

    # 生成报告
    print(f"\n{'='*70}")
    print(f"  生成报告...")
    report = generate_report(results, report_path)
    print(f"📄 报告已写入: {report_path}")

    # 也输出到 stdout
    print(f"\n{report}")


if __name__ == "__main__":
    main()
