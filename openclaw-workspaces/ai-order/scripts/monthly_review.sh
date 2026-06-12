#!/bin/bash
#
# monthly_review.sh — 月度统计报告
#
# 功能：
#   1. 统计本月数据：session 日志数、git commit 数、版本变更数
#   2. 检查 PENDING.md 有无 30+ 天未更新项
#   3. 输出 /tmp/monthly_review_YYYY-MM.md
#
# 触发：launchd 每月 1 号 09:00（或手动）
#
# 用法：
#   bash scripts/monthly_review.sh                # 统计本月
#   bash scripts/monthly_review.sh --month 2026-05  # 统计指定月份

set -e

# 自动检测工作区（优先环境变量，回退到脚本相对路径）
WORKSPACE="${AI_ORDER_WORKSPACE:-$(cd "$(dirname "$0")/.." && pwd)}"
MEMORY_DIR="$WORKSPACE/memory"
PENDING_MD="$WORKSPACE/memory/projects/ai-order/problems/PENDING.md"

# 确定统计月份
if [[ "$1" == "--month" && -n "$2" ]]; then
    TARGET_MONTH="$2"
else
    TARGET_MONTH=$(date +%Y-%m)
fi

# 月份的第一天和最后一天
MONTH_START="${TARGET_MONTH}-01"
# 计算月末（macOS / GNU date 兼容）
# macOS date: -v 必须在 -f 前面
if date -j -v+1m -v-1d -f "%Y-%m-%d" "${MONTH_START}" +%Y-%m-%d >/dev/null 2>&1; then
    MONTH_END=$(date -j -v+1m -v-1d -f "%Y-%m-%d" "${MONTH_START}" +%Y-%m-%d)
else
    # GNU date
    MONTH_END=$(date -d "${MONTH_START} +1 month -1 day" +%Y-%m-%d)
fi

OUTPUT_FILE="/tmp/monthly_review_${TARGET_MONTH}.md"

echo "📊 monthly_review.sh — $TARGET_MONTH 月度统计"
echo "   范围：$MONTH_START ~ $MONTH_END"
echo ""

# === 1. Session 日志数 ===
SESSION_COUNT=0
for f in "$MEMORY_DIR"/${TARGET_MONTH}*.md; do
    [[ -f "$f" ]] || continue
    SESSION_COUNT=$((SESSION_COUNT + 1))
done

# === 2. Git commit 数 ===
cd "$WORKSPACE"
GIT_COMMITS=0
if git rev-parse --git-dir >/dev/null 2>&1; then
    # --after 排他（>），--before 排他（<），用 MONTH_END+1 天作为 before
    if date -j -v+1d -f "%Y-%m-%d" "${MONTH_END}" +%Y-%m-%d >/dev/null 2>&1; then
        GIT_BEFORE=$(date -j -v+1d -f "%Y-%m-%d" "${MONTH_END}" +%Y-%m-%d)
    else
        GIT_BEFORE=$(date -d "${MONTH_END} +1 day" +%Y-%m-%d 2>/dev/null || echo "${MONTH_END}")
    fi
    GIT_COMMITS=$(git log --oneline --after="${MONTH_START}" --before="${GIT_BEFORE}" 2>/dev/null | wc -l | tr -d ' ')
fi

# === 3. 版本变更数 ===
VERSION_CHANGES=0
CHANGELOG="$WORKSPACE/skills/skill_order_to_huading_template/CHANGELOG.md"
if [[ -f "$CHANGELOG" ]]; then
    VERSION_CHANGES=$(grep -c "^## " "$CHANGELOG" 2>/dev/null || echo 0)
fi

# === 4. PENDING.md 30+ 天未更新检查 ===
STALE_ITEMS=0
STALE_DETAILS=""
if [[ -f "$PENDING_MD" ]]; then
    PENDING_MTIME=$(stat -f %m "$PENDING_MD" 2>/dev/null || stat -c %Y "$PENDING_MD" 2>/dev/null)
    NOW=$(date +%s)
    DAYS_SINCE=$(( (NOW - PENDING_MTIME) / 86400 ))

    if [[ $DAYS_SINCE -gt 30 ]]; then
        STALE_ITEMS=1
        STALE_DETAILS="PENDING.md 已 ${DAYS_SINCE} 天未更新"
    fi
else
    STALE_DETAILS="PENDING.md 不存在"
fi

# === 生成报告 ===
cat > "$OUTPUT_FILE" << EOF
# 月度报告 — $TARGET_MONTH

> 生成时间：$(date +%Y-%m-%d\ %H:%M)

## 📈 统计

| 指标 | 数值 |
|------|------|
| Session 日志数 | $SESSION_COUNT |
| Git Commit 数 | $GIT_COMMITS |
| 版本变更记录 | $VERSION_CHANGES |

## ⚠️ 待关注

EOF

if [[ $STALE_ITEMS -gt 0 ]]; then
    echo "- 🔴 $STALE_DETAILS" >> "$OUTPUT_FILE"
else
    echo "- ✅ PENDING.md 状态正常" >> "$OUTPUT_FILE"
fi

echo "" >> "$OUTPUT_FILE"
echo "---" >> "$OUTPUT_FILE"
echo "*报告输出：$OUTPUT_FILE*" >> "$OUTPUT_FILE"

echo "✅ 报告已生成：$OUTPUT_FILE"
echo ""
echo "📋 摘要："
echo "   Session 日志：$SESSION_COUNT"
echo "   Git Commits：$GIT_COMMITS"
echo "   版本变更：$VERSION_CHANGES"
if [[ -n "$STALE_DETAILS" && $STALE_ITEMS -gt 0 ]]; then
    echo "   ⚠️  $STALE_DETAILS"
fi
