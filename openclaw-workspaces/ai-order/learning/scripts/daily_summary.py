#!/usr/bin/env python3
"""
自学习模块 — 每日别名表汇总

功能：
1. 查昨天的 order_corrections（correction_type='sku'）
2. 统计 (entity_name, corrected_value) 出现次数
3. ≥ 2 次的生成建议
4. 输出到 /tmp/alias_summary_YYYYMMDD.md

触发：每天 10:00（cron）

用法：
    python3 learning/scripts/daily_summary.py
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
_ANALYSIS_CONFIG_PATH = os.path.join(_WORKSPACE, "learning", "config", "analysis_config.yaml")
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


def daily_alias_summary():
    """每日别名表汇总（参数从 analysis_config.yaml 读取）"""
    cfg = _analysis_cfg.get("daily_alias_summary", {})
    lookback_days = cfg.get("lookback_days", 1)
    min_count = cfg.get("min_correction_count", 2)

    conn = get_db_connection()
    if not conn:
        return None

    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT entity_name, corrected_value, COUNT(*) as cnt
            FROM order_corrections
            WHERE correction_type = 'sku'
              AND created_at >= CURRENT_DATE - INTERVAL '%s days'
              AND created_at < CURRENT_DATE
            GROUP BY entity_name, corrected_value
            HAVING COUNT(*) >= %s
            ORDER BY cnt DESC
        """, (lookback_days, min_count))
        rows = cur.fetchall()
        cur.close()

        if not rows:
            print("昨日无别名表改进建议")
            return None

        # 生成 Markdown
        today = datetime.date.today().strftime("%Y%m%d")
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

        md = f"# 别名表改进建议（{yesterday} 汇总）\n\n"
        md += "| 订单商品名 | 正确 SKU 名 | 纠正次数 |\n"
        md += "|-----------|------------|--------|\n"
        for r in rows:
            md += f"| {r[0]} | {r[1]} | {r[2]} |\n"

        md += "\n→ 回复\"确认\"执行 / \"跳过\"忽略\n"

        # 写入文件
        output_path = f"/tmp/alias_summary_{today}.md"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(md)

        print(f"别名表汇总已写入: {output_path}")
        return output_path

    except Exception as e:
        print(f"[ERROR] daily_alias_summary failed: {e}")
        return None
    finally:
        conn.close()


if __name__ == "__main__":
    daily_alias_summary()
