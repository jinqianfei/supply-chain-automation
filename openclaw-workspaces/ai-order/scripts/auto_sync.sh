#!/bin/bash
# ============================================================
# 阿里云端自动同步脚本
# 放在阿里云 ECS 上，配合 crontab 使用
#
# crontab -e 添加:
#   */5 * * * * /root/openclaw-workspaces/ai-order/scripts/auto_sync.sh
#
# 功能:
#   1. git pull 拉取最新代码
#   2. 检查并执行 migrations/ 下的新 SQL
#   3. 有变更时重启 OpenClaw
#   4. 记录日志
# ============================================================

set -e

WORKSPACE="/root/openclaw-workspaces/ai-order"
LOG_FILE="/var/log/ai-order-sync.log"
MIGRATION_TRACK="$WORKSPACE/.migration_last_run"
GIT_BRANCH="main"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"; }

cd "$WORKSPACE"

# Step 1: git pull
BEFORE=$(git rev-parse HEAD 2>/dev/null || echo "none")
git pull origin "$GIT_BRANCH" --ff-only 2>/dev/null
AFTER=$(git rev-parse HEAD 2>/dev/null || echo "none")

if [ "$BEFORE" = "$AFTER" ]; then
    # 无更新，静默退出
    exit 0
fi

log "更新检测到: $BEFORE → $AFTER"

# Step 2: 执行数据库迁移
if [ -d "$WORKSPACE/migrations" ]; then
    LAST_RUN=""
    [ -f "$MIGRATION_TRACK" ] && LAST_RUN=$(cat "$MIGRATION_TRACK")

    for sql_file in $(ls -1 "$WORKSPACE/migrations/"*.sql 2>/dev/null | sort); do
        FILE_BASENAME=$(basename "$sql_file")
        if [ -z "$LAST_RUN" ] || [[ "$FILE_BASENAME" > "$LAST_RUN" ]]; then
            log "执行迁移: $FILE_BASENAME"
            source "$WORKSPACE/.env"
            PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$sql_file" >> "$LOG_FILE" 2>&1
            echo "$FILE_BASENAME" > "$MIGRATION_TRACK"
            log "迁移完成: $FILE_BASENAME"
        fi
    done
fi

# Step 3: 重启 OpenClaw
log "重启 OpenClaw..."
openclaw gateway restart >> "$LOG_FILE" 2>&1 || {
    systemctl restart openclaw >> "$LOG_FILE" 2>&1 || {
        log "⚠️ 重启失败"
        exit 1
    }
}

VERSION=$(cat "$WORKSPACE/skills/skill_order_to_huading_template/VERSION" 2>/dev/null || echo "unknown")
log "✅ 同步完成 | commit=$AFTER | version=$VERSION"
