#!/usr/bin/env python3
"""
accuracy_comparison.py — 准确率对比报告脚本

接收两个版本号参数（旧版本、新版本），
从 order_feedback 按版本号分组，
对比两个版本的匹配率、确认率、纠正率，
输出对比报告。

用法:
    python3 skills/skill_order_to_huading_template/scripts/accuracy_comparison.py 5.11.2 5.13.2

可选参数:
    --output /path/to/report.md    输出文件路径（默认 /tmp/accuracy_comparison_YYYYMMDD.md）
    --json                         同时输出 JSON 格式
"""
import sys
import os
import argparse
import datetime
import json as json_mod
from pathlib import Path

# ── 路径 & .env ──
def _detect_workspace() -> Path:
    """自动检测工作区根目录（无硬编码路径）"""
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

import psycopg2


def get_db_config():
    return {
        "host": os.environ.get("DB_HOST"),
        "port": int(os.environ.get("DB_PORT", "5432")),
        "database": os.environ.get("DB_NAME", "neo"),
        "user": os.environ.get("DB_USER", "agenthub"),
        "password": os.environ.get("DB_PASSWORD", ""),
    }


def normalize_version(v):
    """标准化版本号：去掉 v 前缀，统一格式"""
    if v is None:
        return None
    v = str(v).strip()
    if v.lower().startswith("v"):
        v = v[1:]
    return v


def version_match(db_version, target_version):
    """检查数据库中的版本号是否匹配目标版本"""
    if db_version is None or target_version is None:
        return False
    return normalize_version(db_version) == normalize_version(target_version)


def fetch_version_stats(db_config, version):
    """获取指定版本的所有 order_feedback 统计数据"""
    conn = psycopg2.connect(**db_config)
    cur = conn.cursor()

    norm_v = normalize_version(version)

    # 查询所有该版本的记录
    cur.execute("""
        SELECT id, order_date, source_file, output_file, owner_code,
               sku_count, matched_sku_count, sku_match_rate,
               store_count, matched_store_count, store_match_rate,
               user_confirmed, user_modified,
               jsonb_array_length(COALESCE(corrections, '[]'::jsonb)) as corr_count,
               jsonb_array_length(COALESCE(modifications, '[]'::jsonb)) as mod_count,
               skill_version, processing_time_ms,
               session_id, created_at
        FROM order_feedback
        WHERE skill_version IS NOT NULL
        ORDER BY created_at DESC
    """)
    cols = [d[0] for d in cur.description]
    all_rows = [dict(zip(cols, r)) for r in cur.fetchall()]

    # 按版本号过滤（支持模糊匹配）
    rows = [r for r in all_rows if version_match(r["skill_version"], norm_v)]

    # 同时查 corrections 表
    if rows:
        ids = [r["id"] for r in rows]
        placeholders = ",".join(["%s"] * len(ids))
        cur.execute(f"""
            SELECT feedback_id, correction_type, entity_name,
                   original_value, corrected_value, match_layer, match_score,
                   auto_matched
            FROM order_corrections
            WHERE feedback_id IN ({placeholders})
            ORDER BY feedback_id, id
        """, ids)
        corr_cols = [d[0] for d in cur.description]
        corrections = [dict(zip(corr_cols, r)) for r in cur.fetchall()]
    else:
        corrections = []

    cur.close()
    conn.close()

    return rows, corrections


def compute_metrics(feedback_rows, corrections):
    """计算各项指标"""
    total_orders = len(feedback_rows)
    if total_orders == 0:
        return {
            "total_orders": 0,
            "total_sku_items": 0,
            "matched_sku_items": 0,
            "avg_sku_match_rate": 0,
            "perfect_match_orders": 0,
            "total_store_items": 0,
            "matched_store_items": 0,
            "avg_store_match_rate": 0,
            "user_confirmed_count": 0,
            "user_confirmed_rate": 0,
            "user_modified_count": 0,
            "user_modified_rate": 0,
            "total_corrections": len(corrections),
            "correction_by_type": {},
            "avg_corrections_per_order": 0,
            "orders_with_corrections": 0,
            "avg_processing_time_ms": 0,
        }

    total_sku_items = sum(r["sku_count"] or 0 for r in feedback_rows)
    matched_sku_items = sum(r["matched_sku_count"] or 0 for r in feedback_rows)
    total_store_items = sum(r["store_count"] or 0 for r in feedback_rows)
    matched_store_items = sum(r["matched_store_count"] or 0 for r in feedback_rows)

    # 完美匹配（100% SKU 匹配率）的订单数
    perfect_match_orders = sum(1 for r in feedback_rows
                                if r["sku_match_rate"] is not None and r["sku_match_rate"] >= 1.0)

    user_confirmed_count = sum(1 for r in feedback_rows if r["user_confirmed"])
    user_modified_count = sum(1 for r in feedback_rows if r["user_modified"])

    # 纠正分类统计
    correction_by_type = {}
    for c in corrections:
        ct = c["correction_type"] or "unknown"
        correction_by_type[ct] = correction_by_type.get(ct, 0) + 1

    orders_with_corrections = len(set(c["feedback_id"] for c in corrections))

    avg_proc_time = (sum(r["processing_time_ms"] or 0 for r in feedback_rows) / total_orders)

    # 平均 SKU 匹配率（按订单平均）
    rates = [r["sku_match_rate"] for r in feedback_rows if r["sku_match_rate"] is not None]
    avg_sku_rate = sum(rates) / len(rates) if rates else 0

    store_rates = [r["store_match_rate"] for r in feedback_rows if r["store_match_rate"] is not None]
    avg_store_rate = sum(store_rates) / len(store_rates) if store_rates else 0

    return {
        "total_orders": total_orders,
        "total_sku_items": total_sku_items,
        "matched_sku_items": matched_sku_items,
        "overall_sku_match_rate": (matched_sku_items / total_sku_items * 100) if total_sku_items > 0 else 0,
        "avg_sku_match_rate": avg_sku_rate * 100,
        "perfect_match_orders": perfect_match_orders,
        "perfect_match_rate": (perfect_match_orders / total_orders * 100),
        "total_store_items": total_store_items,
        "matched_store_items": matched_store_items,
        "overall_store_match_rate": (matched_store_items / total_store_items * 100) if total_store_items > 0 else 0,
        "avg_store_match_rate": avg_store_rate * 100,
        "user_confirmed_count": user_confirmed_count,
        "user_confirmed_rate": (user_confirmed_count / total_orders * 100),
        "user_modified_count": user_modified_count,
        "user_modified_rate": (user_modified_count / total_orders * 100),
        "total_corrections": len(corrections),
        "correction_by_type": correction_by_type,
        "avg_corrections_per_order": len(corrections) / total_orders,
        "orders_with_corrections": orders_with_corrections,
        "correction_order_rate": (orders_with_corrections / total_orders * 100),
        "avg_processing_time_ms": avg_proc_time,
    }


def generate_comparison_report(old_version, new_version, old_metrics, new_metrics, output_path):
    """生成 Markdown 对比报告"""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def delta(old_val, new_val, fmt=".1f", suffix="%"):
        """计算变化量和变化率"""
        diff = new_val - old_val
        if old_val != 0:
            pct = (diff / old_val) * 100
            arrow = "📈" if diff > 0 else ("📉" if diff < 0 else "➡️")
            return f"{arrow} {diff:+{fmt}}{suffix} ({pct:+.1f}%)"
        else:
            if diff > 0:
                return f"📈 +{new_val:{fmt}}{suffix} (新增)"
            return f"➡️ 0"

    lines = []
    lines.append(f"# 准确率对比报告: v{old_version} → v{new_version}")
    lines.append(f"")
    lines.append(f"**生成时间**: {now}")
    lines.append(f"")

    # ── 样本量 ──
    lines.append(f"## 1. 样本量")
    lines.append(f"")
    lines.append(f"| 指标 | v{old_version} | v{new_version} | 变化 |")
    lines.append(f"|------|-------------|-------------|------|")
    lines.append(f"| 订单数 | {old_metrics['total_orders']} | {new_metrics['total_orders']} | "
                 f"{new_metrics['total_orders'] - old_metrics['total_orders']:+d} |")
    lines.append(f"| SKU 商品总数 | {old_metrics['total_sku_items']} | {new_metrics['total_sku_items']} | "
                 f"{new_metrics['total_sku_items'] - old_metrics['total_sku_items']:+d} |")
    lines.append(f"| 门店总数 | {old_metrics['total_store_items']} | {new_metrics['total_store_items']} | "
                 f"{new_metrics['total_store_items'] - old_metrics['total_store_items']:+d} |")
    lines.append(f"")

    # ── SKU 匹配率 ──
    lines.append(f"## 2. SKU 匹配率")
    lines.append(f"")
    lines.append(f"| 指标 | v{old_version} | v{new_version} | 变化 |")
    lines.append(f"|------|-------------|-------------|------|")

    old_sku_hit = old_metrics.get("overall_sku_match_rate", 0)
    new_sku_hit = new_metrics.get("overall_sku_match_rate", 0)
    lines.append(f"| 整体 SKU 匹配率 | {old_sku_hit:.1f}% | {new_sku_hit:.1f}% | "
                 f"{delta(old_sku_hit, new_sku_hit)} |")

    lines.append(f"| 平均 SKU 匹配率(按订单) | {old_metrics['avg_sku_match_rate']:.1f}% | "
                 f"{new_metrics['avg_sku_match_rate']:.1f}% | "
                 f"{delta(old_metrics['avg_sku_match_rate'], new_metrics['avg_sku_match_rate'])} |")

    lines.append(f"| 100% 匹配订单数 | {old_metrics['perfect_match_orders']} | "
                 f"{new_metrics['perfect_match_orders']} | "
                 f"{new_metrics['perfect_match_orders'] - old_metrics['perfect_match_orders']:+d} |")

    lines.append(f"| 完美匹配率 | {old_metrics['perfect_match_rate']:.1f}% | "
                 f"{new_metrics['perfect_match_rate']:.1f}% | "
                 f"{delta(old_metrics['perfect_match_rate'], new_metrics['perfect_match_rate'])} |")
    lines.append(f"")

    # ── 门店匹配率 ──
    lines.append(f"## 3. 门店匹配率")
    lines.append(f"")
    lines.append(f"| 指标 | v{old_version} | v{new_version} | 变化 |")
    lines.append(f"|------|-------------|-------------|------|")

    old_store_hit = old_metrics.get("overall_store_match_rate", 0)
    new_store_hit = new_metrics.get("overall_store_match_rate", 0)
    lines.append(f"| 整体门店匹配率 | {old_store_hit:.1f}% | {new_store_hit:.1f}% | "
                 f"{delta(old_store_hit, new_store_hit)} |")

    lines.append(f"| 平均门店匹配率(按订单) | {old_metrics['avg_store_match_rate']:.1f}% | "
                 f"{new_metrics['avg_store_match_rate']:.1f}% | "
                 f"{delta(old_metrics['avg_store_match_rate'], new_metrics['avg_store_match_rate'])} |")
    lines.append(f"")

    # ── 确认率 ──
    lines.append(f"## 4. 用户确认率")
    lines.append(f"")
    lines.append(f"| 指标 | v{old_version} | v{new_version} | 变化 |")
    lines.append(f"|------|-------------|-------------|------|")

    lines.append(f"| 用户确认订单数 | {old_metrics['user_confirmed_count']} | "
                 f"{new_metrics['user_confirmed_count']} | "
                 f"{new_metrics['user_confirmed_count'] - old_metrics['user_confirmed_count']:+d} |")

    lines.append(f"| 用户确认率 | {old_metrics['user_confirmed_rate']:.1f}% | "
                 f"{new_metrics['user_confirmed_rate']:.1f}% | "
                 f"{delta(old_metrics['user_confirmed_rate'], new_metrics['user_confirmed_rate'])} |")

    lines.append(f"| 用户修改订单数 | {old_metrics['user_modified_count']} | "
                 f"{new_metrics['user_modified_count']} | "
                 f"{new_metrics['user_modified_count'] - old_metrics['user_modified_count']:+d} |")

    lines.append(f"| 用户修改率 | {old_metrics['user_modified_rate']:.1f}% | "
                 f"{new_metrics['user_modified_rate']:.1f}% | "
                 f"{delta(old_metrics['user_modified_rate'], new_metrics['user_modified_rate'])} |")
    lines.append(f"")

    # ── 纠正率 ──
    lines.append(f"## 5. 纠正率")
    lines.append(f"")
    lines.append(f"| 指标 | v{old_version} | v{new_version} | 变化 |")
    lines.append(f"|------|-------------|-------------|------|")

    lines.append(f"| 总纠正数 | {old_metrics['total_corrections']} | "
                 f"{new_metrics['total_corrections']} | "
                 f"{new_metrics['total_corrections'] - old_metrics['total_corrections']:+d} |")

    lines.append(f"| 有纠正的订单数 | {old_metrics['orders_with_corrections']} | "
                 f"{new_metrics['orders_with_corrections']} | "
                 f"{new_metrics['orders_with_corrections'] - old_metrics['orders_with_corrections']:+d} |")

    lines.append(f"| 纠正订单占比 | {old_metrics.get('correction_order_rate', 0):.1f}% | "
                 f"{new_metrics.get('correction_order_rate', 0):.1f}% | "
                 f"{delta(old_metrics.get('correction_order_rate', 0), new_metrics.get('correction_order_rate', 0))} |")

    lines.append(f"| 平均每订单纠正数 | {old_metrics['avg_corrections_per_order']:.2f} | "
                 f"{new_metrics['avg_corrections_per_order']:.2f} | "
                 f"{delta(old_metrics['avg_corrections_per_order'], new_metrics['avg_corrections_per_order'], '.2f', '')} |")
    lines.append(f"")

    # ── 纠正类型明细 ──
    all_corr_types = sorted(set(
        list(old_metrics["correction_by_type"].keys()) +
        list(new_metrics["correction_by_type"].keys())
    ))
    if all_corr_types:
        lines.append(f"### 纠正类型明细")
        lines.append(f"")
        lines.append(f"| 纠正类型 | v{old_version} | v{new_version} | 变化 |")
        lines.append(f"|----------|-------------|-------------|------|")
        for ct in all_corr_types:
            old_ct = old_metrics["correction_by_type"].get(ct, 0)
            new_ct = new_metrics["correction_by_type"].get(ct, 0)
            lines.append(f"| {ct} | {old_ct} | {new_ct} | {new_ct - old_ct:+d} |")
        lines.append(f"")

    # ── 性能 ──
    lines.append(f"## 6. 处理性能")
    lines.append(f"")
    lines.append(f"| 指标 | v{old_version} | v{new_version} | 变化 |")
    lines.append(f"|------|-------------|-------------|------|")
    old_time = old_metrics["avg_processing_time_ms"]
    new_time = new_metrics["avg_processing_time_ms"]
    lines.append(f"| 平均处理时间 | {old_time:.0f}ms | {new_time:.0f}ms | "
                 f"{delta(old_time, new_time, '.0f', 'ms')} |")
    lines.append(f"")

    # ── 总结 ──
    lines.append(f"## 总结")
    lines.append(f"")
    sku_diff = new_sku_hit - old_sku_hit
    corr_diff = new_metrics.get("correction_order_rate", 0) - old_metrics.get("correction_order_rate", 0)

    if sku_diff > 0:
        lines.append(f"- ✅ SKU 匹配率提升 {sku_diff:.1f} 个百分点")
    elif sku_diff < 0:
        lines.append(f"- ⚠️ SKU 匹配率下降 {abs(sku_diff):.1f} 个百分点")
    else:
        lines.append(f"- ➡️ SKU 匹配率持平")

    if corr_diff < 0:
        lines.append(f"- ✅ 纠正订单占比降低 {abs(corr_diff):.1f} 个百分点（质量提升）")
    elif corr_diff > 0:
        lines.append(f"- ⚠️ 纠正订单占比上升 {corr_diff:.1f} 个百分点")
    else:
        lines.append(f"- ➡️ 纠正订单占比持平")

    confirm_diff = new_metrics["user_confirmed_rate"] - old_metrics["user_confirmed_rate"]
    if confirm_diff > 0:
        lines.append(f"- ✅ 用户确认率提升 {confirm_diff:.1f} 个百分点")
    elif confirm_diff < 0:
        lines.append(f"- ⚠️ 用户确认率下降 {abs(confirm_diff):.1f} 个百分点")
    lines.append(f"")

    report = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    return report


def main():
    parser = argparse.ArgumentParser(description="准确率对比报告: 比较两个版本的 order_feedback 指标")
    parser.add_argument("old_version", help="旧版本号 (如 5.11.2)")
    parser.add_argument("new_version", help="新版本号 (如 5.13.2)")
    parser.add_argument("--output", help="输出文件路径", default=None)
    parser.add_argument("--json", action="store_true", help="同时输出 JSON 格式")
    args = parser.parse_args()

    today = datetime.datetime.now().strftime("%Y%m%d")
    output_path = args.output or f"/tmp/accuracy_comparison_{today}.md"

    print("=" * 70)
    print(f"  准确率对比: v{args.old_version} → v{args.new_version}")
    print("=" * 70)

    db_config = get_db_config()

    # 获取旧版本数据
    print(f"\n📊 获取 v{args.old_version} 数据...")
    old_rows, old_corrections = fetch_version_stats(db_config, args.old_version)
    print(f"    订单数: {len(old_rows)}, 纠正数: {len(old_corrections)}")

    # 获取新版本数据
    print(f"📊 获取 v{args.new_version} 数据...")
    new_rows, new_corrections = fetch_version_stats(db_config, args.new_version)
    print(f"    订单数: {len(new_rows)}, 纠正数: {len(new_corrections)}")

    if not old_rows:
        print(f"\n⚠️  v{args.old_version} 没有找到任何 order_feedback 记录")
        print(f"   可用版本号:")
        # 列出所有版本
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()
        cur.execute("SELECT skill_version, COUNT(*) FROM order_feedback GROUP BY skill_version ORDER BY skill_version")
        for r in cur.fetchall():
            print(f"   - {r[0]}: {r[1]} 条")
        cur.close()
        conn.close()

    if not new_rows:
        print(f"\n⚠️  v{args.new_version} 没有找到任何 order_feedback 记录")

    # 计算指标
    old_metrics = compute_metrics(old_rows, old_corrections)
    new_metrics = compute_metrics(new_rows, new_corrections)

    # 生成报告
    print(f"\n📄 生成对比报告...")
    report = generate_comparison_report(
        args.old_version, args.new_version,
        old_metrics, new_metrics, output_path
    )
    print(f"✅ 报告已写入: {output_path}")

    # JSON 输出
    if args.json:
        json_path = output_path.replace(".md", ".json")
        json_data = {
            "old_version": args.old_version,
            "new_version": args.new_version,
            "generated_at": datetime.datetime.now().isoformat(),
            "old_metrics": old_metrics,
            "new_metrics": new_metrics,
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json_mod.dump(json_data, f, ensure_ascii=False, indent=2)
        print(f"✅ JSON 已写入: {json_path}")

    # 输出报告
    print(f"\n{report}")


if __name__ == "__main__":
    main()
