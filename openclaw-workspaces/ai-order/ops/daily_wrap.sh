#!/bin/bash
#
# daily_wrap.sh — AI建单助手 每日 10:00 自动日结
#
# 用途：
#   1. 检测 session 日志断档（check_continuity.sh）
#   2. 汇总**昨天**（yesterday）的数据库数据
#   3. 生成日结报告（飞书发送 + 写文件）
#   4. 更新 MEMORY.md "最后更新" 时间戳
#
# 触发：crontab 每天 10:00
#   0 10 * * * $WORKSPACE/ops/daily_wrap.sh
#
# 自定义：
#   bash ops/daily_wrap.sh                  # 总结昨天
#   bash ops/daily_wrap.sh --date 2026-06-07 # 总结指定日期
#   bash ops/daily_wrap.sh --no-feishu       # 不发飞书（dry-run）
#   bash ops/daily_wrap.sh --owner HZxxx     # 限定货主

set -e

WORKSPACE="${AI_ORDER_WORKSPACE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SCRIPTS_DIR="$WORKSPACE/ops"
MEMORY_DIR="$WORKSPACE/memory"
MEMORY_MD="$WORKSPACE/MEMORY.md"
DB_CONFIG_PSQL="psql -h localhost -U jinqianfei -d neo"

SEND_FEISHU=true
TARGET_DATE=$(date -v-1d +%Y-%m-%d 2>/dev/null || date -d "yesterday" +%Y-%m-%d)
OWNER_FILTER=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --date) TARGET_DATE="$2"; shift 2;;
    --no-feishu) SEND_FEISHU=false; shift;;
    --owner) OWNER_FILTER="$2"; shift 2;;
    *) echo "未知参数: $1"; exit 1;;
  esac
done

echo "═══════════════════════════════════════════════════════"
echo "  AI建单助手 — 每日日结（总结 $TARGET_DATE 数据）"
echo "  执行时间: $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "═══════════════════════════════════════════════════════"
echo ""

# ── 1. 断档检测 ──
echo "▶ Step 1: 断档检测"
CONTINUITY_RESULT=$(bash "$SCRIPTS_DIR/check_continuity.sh" --no-feishu 2>&1) || CONTINUE_EXIT=$?
CONTINUITY_EXIT=${CONTINUE_EXIT:-0}
echo "$CONTINUITY_RESULT" | sed 's/^/  /'
echo ""

# ── 2. 汇总昨天数据库 ──
echo "▶ Step 2: 汇总 $TARGET_DATE 数据库数据"
REPORT_FILE="/tmp/daily_wrap_${TARGET_DATE}.md"

{
  echo "# 每日日结报告 — $TARGET_DATE"
  echo ""
  echo "**生成时间**：$(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "**数据范围**：$TARGET_DATE 00:00:00 ~ $TARGET_DATE 23:59:59"
  echo ""

  # 2.1 order_feedback 主表汇总
  echo "## 📦 订单处理汇总"
  echo ""
  echo '```sql'
  echo "-- 订单总数 / 货主分布 / 订单类型 / 匹配率 / 修改率"
  echo '```'
  echo ""

  $DB_CONFIG_PSQL -t -A -F'|' <<EOF
SELECT 'orders_total', COUNT(*)::text FROM order_feedback WHERE order_date = DATE '$TARGET_DATE' $( [ -n "$OWNER_FILTER" ] && echo "AND owner_code = '$OWNER_FILTER'" )
UNION ALL
SELECT 'unique_stores', COUNT(DISTINCT owner_code)::text FROM order_feedback WHERE order_date = DATE '$TARGET_DATE' $( [ -n "$OWNER_FILTER" ] && echo "AND owner_code = '$OWNER_FILTER'" )
UNION ALL
SELECT 'auto_confirmed', SUM(CASE WHEN user_confirmed AND NOT user_modified THEN 1 ELSE 0 END)::text FROM order_feedback WHERE order_date = DATE '$TARGET_DATE' $( [ -n "$OWNER_FILTER" ] && echo "AND owner_code = '$OWNER_FILTER'" )
UNION ALL
SELECT 'user_modified', SUM(CASE WHEN user_modified THEN 1 ELSE 0 END)::text FROM order_feedback WHERE order_date = DATE '$TARGET_DATE' $( [ -n "$OWNER_FILTER" ] && echo "AND owner_code = '$OWNER_FILTER'" )
UNION ALL
SELECT 'avg_sku_match_rate', ROUND(AVG(sku_match_rate)::numeric, 3)::text FROM order_feedback WHERE order_date = DATE '$TARGET_DATE' AND sku_count > 0 $( [ -n "$OWNER_FILTER" ] && echo "AND owner_code = '$OWNER_FILTER'" )
UNION ALL
SELECT 'avg_processing_ms', ROUND(AVG(processing_time_ms)::numeric, 0)::text FROM order_feedback WHERE order_date = DATE '$TARGET_DATE' $( [ -n "$OWNER_FILTER" ] && echo "AND owner_code = '$OWNER_FILTER'" )
UNION ALL
SELECT 'total_skus', SUM(sku_count)::text FROM order_feedback WHERE order_date = DATE '$TARGET_DATE' $( [ -n "$OWNER_FILTER" ] && echo "AND owner_code = '$OWNER_FILTER'" )
UNION ALL
SELECT 'total_unmatched', COALESCE(SUM(unmatched_count), 0)::text FROM (
  SELECT jsonb_array_length(COALESCE(NULLIF(alerts, '[]'::jsonb), '[]'::jsonb)) AS unmatched_count
  FROM order_feedback WHERE order_date = DATE '$TARGET_DATE' $( [ -n "$OWNER_FILTER" ] && echo "AND owner_code = '$OWNER_FILTER'" )
) t;
EOF
  echo ""

  # 2.2 order_corrections 用户纠正
  echo "## ✏️ 用户纠正记录"
  echo ""
  $DB_CONFIG_PSQL -t -A -F'|' <<EOF
SELECT correction_type, entity_name, original_value, corrected_value, match_layer, match_score, created_at
FROM order_corrections
WHERE DATE(created_at) = DATE '$TARGET_DATE'
ORDER BY created_at DESC
LIMIT 20;
EOF
  echo ""

  # 2.3 layer_success_rate 层成功率
  echo "## 📈 匹配层成功率（$TARGET_DATE 累计）"
  echo ""
  $DB_CONFIG_PSQL -t -A -F'|' <<EOF
SELECT entity_type, layer_name, layer_description, total_attempts, success_count, user_corrected_count, success_rate, avg_match_score
FROM layer_success_rate
ORDER BY entity_type, layer_name;
EOF
  echo ""

  # 2.4 断档检测结果
  echo "## 🩺 断档检测"
  echo ""
  echo '```'
  echo "$CONTINUITY_RESULT"
  echo '```'
  echo ""

  # 2.5 总结建议
  echo "## 💡 AI 建议"
  echo ""
  # 这里可以放 AI 分析代码，但本脚本只生成数据
  echo "（待 AI 在收到本报告后生成）"

} > "$REPORT_FILE"

echo "  ✅ 报告已生成: $REPORT_FILE"
echo "  📄 内容预览："
sed 's/^/    /' "$REPORT_FILE" | head -40
echo ""

# ── 3. 发飞书 ──
if [ "$SEND_FEISHU" = true ]; then
  echo "▶ Step 3: 飞书日结推送"
  REPORT_CONTENT=$(cat "$REPORT_FILE")
  MSG="【AI建单助手 · $TARGET_DATE 日结】\n\n$REPORT_CONTENT\n\n查看完整报告: file://$REPORT_FILE"

  if [ -n "$OPENCLAW_FEISHU_WEBHOOK" ]; then
    curl -sS -X POST "$OPENCLAW_FEISHU_WEBHOOK" \
      -H "Content-Type: application/json" \
      -d "$(jq -n --arg c "$MSG" '{msg_type:"text",content:{text:$c}}')" >/dev/null 2>&1 || true
    echo "  ✅ 飞书已推送"
  else
    echo "  ⏭️  未设置 OPENCLAW_FEISHU_WEBHOOK，跳过推送"
  fi
  echo ""
fi

# ── 4. 更新 MEMORY.md 时间戳 ──
echo "▶ Step 4: 更新 MEMORY.md 时间戳"
if [ -f "$MEMORY_MD" ]; then
  # 用 awk 替换"## 最后更新"段的日期
  NEW_TS="$(date '+%Y-%m-%d %H:%M') GMT+8"
  BACKUP="$MEMORY_MD.bak"
  cp "$MEMORY_MD" "$BACKUP"
  awk -v new_ts="$NEW_TS" '
    /^## 最后更新$/ { print; getline; print new_ts; skip=1; next }
    skip && /^[0-9]{4}-/ { next }
    { skip=0; print }
  ' "$BACKUP" > "$MEMORY_MD"
  rm "$BACKUP"
  echo "  ✅ MEMORY.md 时间戳已更新为 $NEW_TS"
else
  echo "  ⚠️  $MEMORY_MD 不存在，跳过"
fi
echo ""

echo "═══════════════════════════════════════════════════════"
echo "  ✅ 每日日结完成"
echo "═══════════════════════════════════════════════════════"

# 退出码：
#   0 = 正常
#   1 = 有警告（WARN，可继续）
#   2 = P0 故障（断档超 72h） — 严重
if [ "$CONTINUITY_EXIT" -ge 2 ]; then
  exit 2
fi
exit 0
