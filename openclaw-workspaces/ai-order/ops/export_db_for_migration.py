#!/usr/bin/env python3
"""
数据库导出脚本 - 导出 AWS RDS 数据为 SQL 文件，方便导入阿里云 RDS
导出内容：表结构 + 数据 + 索引 + 约束
"""
import os
import sys
import json
from datetime import datetime
from pathlib import Path

# 加载 .env
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())

import psycopg2

DB_CONFIG = {
    "host": os.environ["DB_HOST"],
    "port": int(os.environ["DB_PORT"]),
    "database": os.environ["DB_NAME"],
    "user": os.environ["DB_USER"],
    "password": os.environ["DB_PASSWORD"],
}

# 需要优先导出的核心表
CORE_TABLES = [
    "product_sku",
    "product_name_alias",
    "store_list",
    "warehouse_code_mapping",
    "customer",
    "order_feedback",
    "order_corrections",
    "layer_success_rate",
    "self_learning_config",
    "learning_events",
]

OUTPUT_DIR = Path(__file__).parent.parent / "output"


def quote_col(col):
    return '"' + col + '"'


def get_table_ddl(conn, table_name):
    """获取表结构 DDL"""
    cur = conn.cursor()
    cur.execute("""
        SELECT column_name, data_type, character_maximum_length,
               numeric_precision, numeric_scale, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_name = %s
        ORDER BY ordinal_position
    """, (table_name,))
    columns = cur.fetchall()
    if not columns:
        return None

    col_defs = []
    for col in columns:
        name, dtype, max_len, num_prec, num_scale, nullable, default = col
        if dtype == "character varying":
            type_str = f"VARCHAR({max_len})"
        elif dtype == "character":
            type_str = f"CHAR({max_len})"
        elif dtype == "numeric" and num_prec:
            type_str = f"NUMERIC({num_prec},{num_scale})"
        elif dtype in ("integer", "bigint", "smallint", "boolean", "text", "jsonb", "json", "real"):
            type_str = dtype.upper()
        elif dtype == "double precision":
            type_str = "DOUBLE PRECISION"
        elif dtype == "timestamp without time zone":
            type_str = "TIMESTAMP"
        elif dtype == "timestamp with time zone":
            type_str = "TIMESTAMPTZ"
        elif dtype == "date":
            type_str = "DATE"
        else:
            type_str = dtype.upper()

        col_def = f"  {quote_col(name)} {type_str}"
        if default:
            col_def += f" DEFAULT {default}"
        if nullable == "NO":
            col_def += " NOT NULL"
        col_defs.append(col_def)

    # 主键
    cur.execute("""
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
        WHERE tc.table_name = %s AND tc.constraint_type = 'PRIMARY KEY'
        ORDER BY kcu.ordinal_position
    """, (table_name,))
    pk_cols = [r[0] for r in cur.fetchall()]
    if pk_cols:
        pk_str = ", ".join(quote_col(c) for c in pk_cols)
        col_defs.append(f"  PRIMARY KEY ({pk_str})")

    # 唯一约束
    cur.execute("""
        SELECT tc.constraint_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
        WHERE tc.table_name = %s AND tc.constraint_type = 'UNIQUE'
        ORDER BY tc.constraint_name, kcu.ordinal_position
    """, (table_name,))
    unique_constraints = {}
    for cname, col in cur.fetchall():
        unique_constraints.setdefault(cname, []).append(col)
    for cname, cols in unique_constraints.items():
        uq_str = ", ".join(quote_col(c) for c in cols)
        col_defs.append(f'  CONSTRAINT "{cname}" UNIQUE ({uq_str})')

    ddl = f'CREATE TABLE IF NOT EXISTS "{table_name}" (\n'
    ddl += ",\n".join(col_defs)
    ddl += "\n);\n"
    return ddl


def get_indexes(conn, table_name):
    """获取索引 DDL"""
    cur = conn.cursor()
    cur.execute("""
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE tablename = %s AND indexdef NOT LIKE '%%PRIMARY KEY%%'
    """, (table_name,))
    indexes = []
    for name, definition in cur.fetchall():
        definition = definition.replace("CREATE INDEX", "CREATE INDEX IF NOT EXISTS", 1)
        definition = definition.replace("CREATE UNIQUE INDEX", "CREATE UNIQUE INDEX IF NOT EXISTS", 1)
        indexes.append(f"{definition};\n")
    return indexes


def export_table_data(conn, table_name):
    """导出表数据为 INSERT 语句"""
    cur = conn.cursor()
    cur.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = %s
        ORDER BY ordinal_position
    """, (table_name,))
    columns = [r[0] for r in cur.fetchall()]
    if not columns:
        return [], 0

    col_list = ", ".join(quote_col(c) for c in columns)
    cur.execute(f'SELECT {col_list} FROM "{table_name}"')
    rows = cur.fetchall()

    inserts = []
    batch_size = 100
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        values_list = []
        for row in batch:
            vals = []
            for v in row:
                if v is None:
                    vals.append("NULL")
                elif isinstance(v, bool):
                    vals.append("TRUE" if v else "FALSE")
                elif isinstance(v, (int, float)):
                    vals.append(str(v))
                elif isinstance(v, (dict, list)):
                    json_str = json.dumps(v, ensure_ascii=False).replace("'", "''")
                    vals.append(f"'{json_str}'")
                elif isinstance(v, datetime):
                    vals.append(f"'{v.isoformat()}'")
                else:
                    vals.append(f"'{str(v).replace(chr(39), chr(39)+chr(39))}'")
            values_list.append(f"({', '.join(vals)})")

        insert = f'INSERT INTO "{table_name}" ({col_list}) VALUES\n'
        insert += ",\n".join(values_list)
        insert += "\nON CONFLICT DO NOTHING;\n"
        inserts.append(insert)

    return inserts, len(rows)


def main():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = OUTPUT_DIR / f"migration_export_{timestamp}.sql"
    output_json = OUTPUT_DIR / f"migration_export_{timestamp}.json"

    print(f"🔌 连接数据库: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
    conn = psycopg2.connect(**DB_CONFIG)

    cur = conn.cursor()
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """)
    all_tables = [r[0] for r in cur.fetchall()]
    print(f"📊 发现 {len(all_tables)} 张表")

    # 排序：核心表优先
    tables_to_export = []
    for t in CORE_TABLES:
        if t in all_tables:
            tables_to_export.append(t)
    for t in all_tables:
        if t not in tables_to_export:
            tables_to_export.append(t)

    stats = {}

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"-- AI建单助手 数据库迁移导出\n")
        f.write(f"-- 导出时间: {datetime.now().isoformat()}\n")
        f.write(f"-- 源: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}\n")
        f.write(f"-- 表数: {len(tables_to_export)}\n\n")

        # 1. 表结构
        f.write("-- ==========================================\n")
        f.write("-- 表结构 (DDL)\n")
        f.write("-- ==========================================\n\n")
        for table in tables_to_export:
            ddl = get_table_ddl(conn, table)
            if ddl:
                f.write(f"-- 表: {table}\n")
                f.write(ddl)
                f.write("\n")

        # 2. 索引
        f.write("-- ==========================================\n")
        f.write("-- 索引\n")
        f.write("-- ==========================================\n\n")
        for table in tables_to_export:
            indexes = get_indexes(conn, table)
            if indexes:
                f.write(f"-- 索引: {table}\n")
                for idx in indexes:
                    f.write(idx)
                f.write("\n")

        # 3. 数据
        f.write("-- ==========================================\n")
        f.write("-- 数据\n")
        f.write("-- ==========================================\n\n")
        for table in tables_to_export:
            try:
                inserts, count = export_table_data(conn, table)
                if inserts:
                    f.write(f"-- 数据: {table} ({count} 条)\n")
                    for insert in inserts:
                        f.write(insert)
                    f.write("\n")
                    stats[table] = count
                    print(f"  ✅ {table}: {count} 条")
                else:
                    stats[table] = 0
                    print(f"  ⬜ {table}: 空表")
            except Exception as e:
                print(f"  ❌ {table}: {e}")
                stats[table] = f"ERROR: {e}"

    # 导出统计
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump({
            "export_time": datetime.now().isoformat(),
            "source": f"{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}",
            "tables": stats,
            "total_tables": len(tables_to_export),
            "total_rows": sum(v for v in stats.values() if isinstance(v, int)),
        }, f, ensure_ascii=False, indent=2)

    conn.close()

    sql_size = output_file.stat().st_size / 1024
    print(f"\n✅ 导出完成:")
    print(f"  SQL 文件: {output_file} ({sql_size:.0f} KB)")
    print(f"  统计文件: {output_json}")
    print(f"  总表数: {len(tables_to_export)}")
    total = sum(v for v in stats.values() if isinstance(v, int))
    print(f"  总行数: {total}")
    return str(output_file)


if __name__ == "__main__":
    main()
