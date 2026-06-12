#!/usr/bin/env python3
"""
自学习模块 — 分析脚本

功能：
1. 高频纠正商品 → 别名表候选（滚动 7 天，≥3 次）
2. 层成功率统计（累计全量，≥50 次尝试）
3. 阈值调优建议（滚动 30 天，纠正率排名）
4. 输出 Markdown 报告到 /tmp/analysis_report_YYYYMMDD.md

用法：
    python3 scripts/analyze_learning_data.py
"""
import os
import sys
import datetime
import yaml

# ── 自动检测工作区（无硬编码路径）──
def _detect_workspace():
    env_ws = os.environ.get("AI_ORDER_WORKSPACE")
    if env_ws and os.path.isdir(env_ws):
        return env_ws
    script_dir = os.path.dirname(os.path.abspath(__file__))
    for parent_dir in [script_dir] + [os.path.dirname(p) for p in [
        script_dir,
        os.path.dirname(script_dir),
    ]]:
        candidate = parent_dir if os.path.isdir(os.path.join(parent_dir, "skills")) else None
        if candidate:
            return candidate
    # 向上查找
    check = script_dir
    for _ in range(5):
        check = os.path.dirname(check)
        if os.path.isdir(os.path.join(check, "skills")):
            return check
    return os.getcwd()

_WORKSPACE = _detect_workspace()
_SKILL_ROOT = os.path.join(_WORKSPACE, "skills", "skill_order_to_huading_template")
if _SKILL_ROOT not in sys.path:
    sys.path.insert(0, _SKILL_ROOT)

# ── 加载分析阈值配置 ──
_ANALYSIS_CONFIG_PATH = os.path.join(_WORKSPACE, "config", "analysis_config.yaml")
_analysis_cfg = {}
if os.path.exists(_ANALYSIS_CONFIG_PATH):
    with open(_ANALYSIS_CONFIG_PATH, "r", encoding="utf-8") as f:
        _analysis_cfg = yaml.safe_load(f) or {}

try:
    from db.connection import get_default_db_config
    import psycopg2
except ImportError as e:
    print(f"[ERROR] Import failed: {e}")
    sys.exit(1)


def get_db_connection():
    """获取数据库连接"""
    try:
        config = get_default_db_config()
        return psycopg2.connect(**config)
    except Exception as e:
        print(f"[ERROR] DB connect failed: {e}")
        return None


def analyze_alias_candidates():
    """高频纠正 → 别名表候选（参数从 analysis_config.yaml 读取）"""
    cfg = _analysis_cfg.get("alias_candidates", {})
    lookback_days = cfg.get("lookback_days", 7)
    min_count = cfg.get("min_correction_count", 3)
    max_results = cfg.get("max_results", 20)

    conn = get_db_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT entity_name, corrected_value, COUNT(*) as cnt
            FROM order_corrections
            WHERE correction_type = 'sku'
              AND created_at >= CURRENT_DATE - INTERVAL '%s days'
            GROUP BY entity_name, corrected_value
            HAVING COUNT(*) >= %s
            ORDER BY cnt DESC
            LIMIT %s
        """, (lookback_days, min_count, max_results))
        rows = cur.fetchall()
        cur.close()
        return rows
    except Exception as e:
        print(f"[WARN] analyze_alias_candidates failed: {e}")
        return []
    finally:
        conn.close()


def analyze_layer_success_rate():
    """层成功率统计（参数从 analysis_config.yaml 读取）"""
    cfg = _analysis_cfg.get("layer_success_rate", {})
    min_attempts = cfg.get("min_total_attempts", 50)

    conn = get_db_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT entity_type, layer_name, total_attempts, success_count,
                   user_corrected_count,
                   ROUND(success_rate * 100, 2) as success_pct,
                   ROUND(avg_match_score, 4) as avg_score
            FROM layer_success_rate
            WHERE total_attempts >= %s
            ORDER BY entity_type, success_rate ASC
        """, (min_attempts,))
        rows = cur.fetchall()
        cur.close()
        return rows
    except Exception as e:
        print(f"[WARN] analyze_layer_success_rate failed: {e}")
        return []
    finally:
        conn.close()


def analyze_threshold_tuning():
    """阈值调优建议（参数从 analysis_config.yaml 读取）"""
    cfg = _analysis_cfg.get("threshold_tuning", {})
    lookback_days = cfg.get("lookback_days", 30)
    min_count = cfg.get("min_total_count", 10)
    rate_threshold = cfg.get("correction_rate_threshold", 30)

    conn = get_db_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT match_layer,
              COUNT(*) as total,
              SUM(CASE WHEN auto_matched THEN 1 ELSE 0 END) as confirmed,
              SUM(CASE WHEN NOT auto_matched THEN 1 ELSE 0 END) as corrected,
              ROUND(SUM(CASE WHEN NOT auto_matched THEN 1 ELSE 0 END)::FLOAT / NULLIF(COUNT(*), 0) * 100, 2) as correction_rate
            FROM order_corrections
            WHERE created_at >= CURRENT_DATE - INTERVAL '%s days'
            GROUP BY match_layer
            HAVING COUNT(*) >= %s
            ORDER BY correction_rate DESC
        """, (lookback_days, min_count))
        rows = cur.fetchall()
        cur.close()
        return rows, rate_threshold
    except Exception as e:
        print(f"[WARN] analyze_threshold_tuning failed: {e}")
        return [], 30
    finally:
        conn.close()


def generate_report():
    """生成 Markdown 报告"""
    today = datetime.date.today().strftime("%Y%m%d")
    output_path = f"/tmp/analysis_report_{today}.md"

    lines = []
    lines.append(f"# 自学习模块分析报告（{datetime.date.today()}）\n")

    # 1. 别名表候选
    lines.append("## 1. 别名表改进候选（近 7 天高频纠正）\n")
    alias_candidates = analyze_alias_candidates()
    if alias_candidates:
        lines.append("| 订单商品名 | 正确 SKU 名 | 纠正次数 |")
        lines.append("|-----------|------------|---------|")
        for r in alias_candidates:
            lines.append(f"| {r[0]} | {r[1]} | {r[2]} |")
    else:
        lines.append("*暂无数据（需要积累订单数据）*\n")

    # 2. 层成功率
    lines.append("\n## 2. 层成功率统计（累计，≥50 次尝试）\n")
    layer_stats = analyze_layer_success_rate()
    if layer_stats:
        lines.append("| 实体类型 | 层名 | 尝试次数 | 成功数 | 纠正数 | 成功率% | 平均匹配分 |")
        lines.append("|---------|------|---------|-------|-------|--------|-----------|")
        for r in layer_stats:
            lines.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} | {r[6]} |")
    else:
        lines.append("*暂无数据（需要积累订单数据）*\n")

    # 3. 阈值调优
    threshold_cfg = _analysis_cfg.get("threshold_tuning", {})
    lookback_days = threshold_cfg.get("lookback_days", 30)
    rate_threshold = threshold_cfg.get("correction_rate_threshold", 30)
    lines.append(f"\n## 3. 阈值调优建议（近 {lookback_days} 天，纠正率排名）\n")
    threshold_suggestions, rate_threshold = analyze_threshold_tuning()
    if threshold_suggestions:
        lines.append("| 匹配层 | 总次数 | 确认数 | 纠正数 | 纠正率% |")
        lines.append("|-------|-------|-------|-------|--------|")
        for r in threshold_suggestions:
            lines.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} |")
        lines.append(f"\n*纠正率 > {rate_threshold}% 的层建议降低阈值*")
    else:
        lines.append("*暂无数据（需要积累订单数据）*\n")

    # 写入文件
    report = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"分析报告已写入: {output_path}")
    return output_path


if __name__ == "__main__":
    generate_report()
