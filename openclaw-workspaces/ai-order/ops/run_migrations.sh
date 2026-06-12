#!/bin/bash
# ============================================================
# 数据库迁移执行器
# 执行 migrations/ 目录下尚未执行过的 SQL 文件
#
# 使用方法:
#   bash ops/run_migrations.sh
#
# 迁移文件命名规范:
#   migrations/20260612_001_add_column_xxx.sql
#   migrations/20260612_002_create_table_yyy.sql
#   （按文件名排序执行）
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(dirname "$SCRIPT_DIR")"
MIGRATIONS_DIR="$WORKSPACE/migrations"
TRACK_FILE="$WORKSPACE/.migration_last_run"

# 加载 .env
if [ -f "$WORKSPACE/.env" ]; then
    source "$WORKSPACE/.env"
else
    echo "❌ 找不到 .env 文件"
    exit 1
fi

# 检查 migrations 目录
if [ ! -d "$MIGRATIONS_DIR" ]; then
    echo "📁 创建 migrations/ 目录"
    mkdir -p "$MIGRATIONS_DIR"
    exit 0
fi

# 获取上次执行的最后一个文件
LAST_RUN=""
[ -f "$TRACK_FILE" ] && LAST_RUN=$(cat "$TRACK_FILE")

# 查找待执行的 SQL 文件
PENDING=$(ls -1 "$MIGRATIONS_DIR/"*.sql 2>/dev/null | sort)

if [ -z "$PENDING" ]; then
    echo "✅ 无待执行的迁移文件"
    exit 0
fi

EXECUTED=0
SKIPPED=0

for sql_file in $PENDING; do
    FILE_BASENAME=$(basename "$sql_file")

    # 跳过已执行过的
    if [ -n "$LAST_RUN" ] && [[ ! "$FILE_BASENAME" > "$LAST_RUN" ]]; then
        SKIPPED=$((SKIPPED + 1))
        continue
    fi

    echo "🔄 执行: $FILE_BASENAME"

    # 执行 SQL
    PGPASSWORD="$DB_PASSWORD" psql \
        -h "$DB_HOST" \
        -p "$DB_PORT" \
        -U "$DB_USER" \
        -d "$DB_NAME" \
        -f "$sql_file" \
        --single-transaction \
        2>&1

    if [ $? -eq 0 ]; then
        echo "  ✅ 成功"
        echo "$FILE_BASENAME" > "$TRACK_FILE"
        EXECUTED=$((EXECUTED + 1))
    else
        echo "  ❌ 失败，停止执行后续迁移"
        exit 1
    fi
done

echo ""
echo "📊 迁移结果: 执行 $EXECUTED 个, 跳过 $SKIPPED 个"
