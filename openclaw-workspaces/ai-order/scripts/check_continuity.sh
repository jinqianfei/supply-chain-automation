#!/bin/bash
#
# check_continuity.sh — 记忆系统断档检测
#
# 用途：检测 session 日志是否断档（>24h 无新日志视为 P0 故障）
# 触发：每日 10:00 由 daily_wrap.sh 调用 / 也可手动跑
# 退出码：
#   0 = 正常（最新日志在 24h 内）
#   1 = 警告（24-72h 未更新）
#   2 = P0 故障（>72h 断档）
#
# 用法：
#   bash scripts/check_continuity.sh
#   bash scripts/check_continuity.sh --warn-hours 24  # 自定义警告阈值
#   bash scripts/check_continuity.sh --p0-hours 72    # 自定义 P0 阈值
#   bash scripts/check_continuity.sh --no-feishu      # 不发飞书告警

set -e

WORKSPACE="${WORKSPACE:-/Users/jinqianfei/openclaw-workspaces/ai-order}"
MEMORY_DIR="$WORKSPACE/memory"
WARN_HOURS="${WARN_HOURS:-24}"
P0_HOURS="${P0_HOURS:-72}"
SEND_FEISHU=true

while [[ $# -gt 0 ]]; do
  case $1 in
    --warn-hours) WARN_HOURS="$2"; shift 2;;
    --p0-hours) P0_HOURS="$2"; shift 2;;
    --no-feishu) SEND_FEISHU=false; shift;;
    *) echo "未知参数: $1"; exit 1;;
  esac
done

# 1. 找最近的 session 日志
LAST_LOG=$(ls -t "$MEMORY_DIR"/2026-*.md 2>/dev/null | head -1 || echo "")

if [ -z "$LAST_LOG" ]; then
  echo "🚨 P0：找不到任何 session 日志（$MEMORY_DIR/2026-*.md 不存在）"
  exit 2
fi

LAST_FILENAME=$(basename "$LAST_LOG")
# 从文件名提取日期（支持 YYYY-MM-DD 和 YYYY-MM-DD-to-DD 两种格式）
LAST_DATE=$(echo "$LAST_FILENAME" | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}' | head -1)

if [ -z "$LAST_DATE" ]; then
  echo "⚠️  无法从日志文件名解析日期: $LAST_FILENAME"
  exit 1
fi

# 2. 计算天数差
NOW_EPOCH=$(date +%s)
LAST_EPOCH=$(date -j -f "%Y-%m-%d" "$LAST_DATE" +%s 2>/dev/null || date -d "$LAST_DATE" +%s 2>/dev/null || echo 0)

if [ "$LAST_EPOCH" -eq 0 ]; then
  echo "⚠️  无法计算日期: $LAST_DATE"
  exit 1
fi

GAP_HOURS=$(( (NOW_EPOCH - LAST_EPOCH) / 3600 ))
GAP_DAYS=$(( GAP_HOURS / 24 ))

echo "📋 断档检测报告"
echo "  最新日志: $LAST_FILENAME"
echo "  最后日期: $LAST_DATE"
echo "  距今:     $GAP_HOURS 小时 (≈ $GAP_DAYS 天)"
echo "  警告阈值: $WARN_HOURS 小时"
echo "  P0 阈值:  $P0_HOURS 小时"

# 3. 判定
if [ "$GAP_HOURS" -gt "$P0_HOURS" ]; then
  STATUS="P0"
  LEVEL=2
  EMOJI="🚨"
elif [ "$GAP_HOURS" -gt "$WARN_HOURS" ] || { [ "$WARN_HOURS" = "0" ] && [ "$GAP_HOURS" -ge 0 ]; }; then
  STATUS="WARN"
  LEVEL=1
  EMOJI="⚠️ "
else
  STATUS="OK"
  LEVEL=0
  EMOJI="✅"
fi

echo ""
echo "$EMOJI 状态：$STATUS（断档 $GAP_HOURS 小时）"

# 4. 飞书告警（仅 P0 / WARN）
if [ "$SEND_FEISHU" = true ] && [ "$LEVEL" -gt 0 ]; then
  MSG="[记忆系统] $EMOJI $STATUS：日志断档 $GAP_HOURS 小时 (最后日志: $LAST_FILENAME)"
  echo ""
  echo "📤 飞书告警：$MSG"
  # 实际发送（用 openclaw 内部消息通道）
  if [ -n "$OPENCLAW_FEISHU_WEBHOOK" ]; then
    curl -sS -X POST "$OPENCLAW_FEISHU_WEBHOOK" \
      -H "Content-Type: application/json" \
      -d "{\"msg_type\":\"text\",\"content\":{\"text\":\"$MSG\"}}" >/dev/null 2>&1 || true
  fi
fi

exit $LEVEL
