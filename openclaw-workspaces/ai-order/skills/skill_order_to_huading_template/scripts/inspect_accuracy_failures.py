#!/usr/bin/env python3
"""Inspect SKU rows involved in the latest accuracy audit failures."""
import os
import sys
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


def load_env():
    env_path = WORKSPACE / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def main():
    load_env()
    import psycopg2
    from db.table_names import SKU_TABLE

    cfg = {
        "host": os.environ.get("DB_HOST"),
        "port": int(os.environ.get("DB_PORT", "5432")),
        "database": os.environ.get("DB_NAME", "neo"),
        "user": os.environ.get("DB_USER", "agenthub"),
        "password": os.environ.get("DB_PASSWORD", ""),
    }
    sku_codes = [
        "SK250214000074",
        "SK241225000055",
        "SK250820000194",
        "SK250327000074",
        "SK250327000076",
    ]
    conn = psycopg2.connect(**cfg)
    cur = conn.cursor()
    cur.execute(f"""
        SELECT sku_code, shipper_id, sku_name, unit, unit_type, conversion_ratio,
               product_spec, customer_code, status
        FROM {SKU_TABLE}
        WHERE sku_code = ANY(%s)
        ORDER BY sku_code, shipper_id, unit_type, unit
    """, (sku_codes,))
    for row in cur.fetchall():
        print("\t".join("" if v is None else str(v) for v in row))
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
