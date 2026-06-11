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
    python3 scripts/daily_alias_summary.py
"""
import os
import sys
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from skills.skill_order_to_huading_template.db.connection import get_default_db_config
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
    """每日别名表汇总"""
    conn = get_db_connection()
    if not conn:
        return None

    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT entity_name, corrected_value, COUNT(*) as cnt
            FROM order_corrections
            WHERE correction_type = 'sku'
              AND created_at >= CURRENT_DATE - INTERVAL '1 day'
              AND created_at < CURRENT_DATE
            GROUP BY entity_name, corrected_value
            HAVING COUNT(*) >= 2
            ORDER BY cnt DESC
        """)
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
