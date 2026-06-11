#!/bin/bash
#
# test_phase2_guards.sh — Phase 2 三个守护脚本的端到端测试
#
# 覆盖：
# 1. check_continuity.sh 的 OK / WARN / P0 三种状态
# 2. daily_wrap.sh 的 --date 自定义日期
# 3. startup_check.py 的 4 项检查
#
# 用法：
#   bash scripts/test_phase2_guards.sh

# 不 set -e：测试要检所有可能退出码，包括 1（WARN）

WORKSPACE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$WORKSPACE/scripts"
MEMORY_DIR="$WORKSPACE/memory"

PASS=0
FAIL=0

ok() { echo "  ✅ $1"; PASS=$((PASS+1)); }
fail() { echo "  ❌ $1"; FAIL=$((FAIL+1)); }
sep() { echo ""; echo "─── $1 ───"; }

# ────────────────────────────────────────
sep "Test 1: check_continuity.sh — OK 状态"
LAST_LOG=$(ls -t "$MEMORY_DIR"/2026-*.md 2>/dev/null | head -1)
if [ -z "$LAST_LOG" ]; then
  fail "未找到任何 session 日志"
else
  ok "找到最新日志: $(basename "$LAST_LOG")"
fi

OUT=$(bash "$SCRIPTS/check_continuity.sh" --no-feishu 2>&1)
EC=$?
if [ "$EC" -eq 0 ] && echo "$OUT" | grep -q "状态：OK"; then
  ok "check_continuity 退出码 0 + 状态 OK"
else
  fail "check_continuity 退出码 $EC，输出：$OUT"
fi

# ────────────────────────────────────────
sep "Test 2: check_continuity.sh — 自定义阈值（无最新日志场景）"
# 用 --warn-hours 0 强制触发 WARN
OUT=$(bash "$SCRIPTS/check_continuity.sh" --warn-hours 0 --no-feishu 2>&1)
EC=$?
if [ "$EC" -ge 1 ] && echo "$OUT" | grep -qE "(WARN|P0)"; then
  ok "阈值收紧时正确触发 WARN/P0（退出码 $EC）"
else
  fail "收紧阈值未触发告警：$OUT"
fi

# ────────────────────────────────────────
sep "Test 3: daily_wrap.sh — 总结昨天"
OUT=$(bash "$SCRIPTS/daily_wrap.sh" --no-feishu 2>&1)
EC=$?
if [ "$EC" -eq 0 ] && echo "$OUT" | grep -q "每日日结完成"; then
  ok "daily_wrap 跑通（总结默认昨天）"
else
  fail "daily_wrap 失败：退出码 $EC"
fi

# ────────────────────────────────────────
sep "Test 4: daily_wrap.sh — 总结指定日期"
OUT=$(bash "$SCRIPTS/daily_wrap.sh" --date 2026-06-01 --no-feishu 2>&1)
EC=$?
if [ "$EC" -eq 0 ] && echo "$OUT" | grep -q "2026-06-01"; then
  ok "daily_wrap --date 自定义日期成功"
else
  fail "daily_wrap --date 失败：$EC"
fi

# ────────────────────────────────────────
sep "Test 5: daily_wrap.sh — 报告文件生成"
YESTERDAY=$(date -v-1d +%Y-%m-%d 2>/dev/null || date -d "yesterday" +%Y-%m-%d)
REPORT="/tmp/daily_wrap_${YESTERDAY}.md"
if [ -f "$REPORT" ]; then
  ok "报告文件存在: $REPORT"
  if grep -q "订单处理汇总" "$REPORT" && grep -q "匹配层成功率" "$REPORT"; then
    ok "报告包含必要章节"
  else
    fail "报告内容不完整"
  fi
else
  fail "报告文件未生成（预期: $REPORT）"
fi

# ────────────────────────────────────────
sep "Test 6: startup_check.py — 4 项检查"
OUT=$(python3 "$SCRIPTS/startup_check.py" 2>&1) || EC=$?
EC=${EC:-0}
if echo "$OUT" | grep -q "version_check"; then
  ok "version_check 项被检查"
else
  fail "缺少 version_check"
fi
if echo "$OUT" | grep -q "git_clean"; then
  ok "git_clean 项被检查"
else
  fail "缺少 git_clean"
fi
if echo "$OUT" | grep -q "memory_fresh"; then
  ok "memory_fresh 项被检查"
else
  fail "缺少 memory_fresh"
fi
if echo "$OUT" | grep -q "no_pending"; then
  ok "no_pending 项被检查"
else
  fail "缺少 no_pending"
fi
if [ "$EC" -le 1 ]; then
  ok "退出码可接受（$EC，0=全过/1=仅警告）"
else
  fail "退出码异常: $EC"
fi

# ────────────────────────────────────────
sep "Test 7: startup_check.py — JSON 输出"
JSON_OUT=$(python3 "$SCRIPTS/startup_check.py" --json 2>&1)
if echo "$JSON_OUT" | python3 -c "import sys, json; d=json.load(sys.stdin); assert 'checks' in d; assert len(d['checks']) == 4" 2>/dev/null; then
  ok "JSON 输出格式正确（4 项 checks）"
else
  fail "JSON 输出格式错误"
fi

# ────────────────────────────────────────
sep "Test 8: launchd 任务已注册"
if launchctl list 2>/dev/null | grep -q "com.ai-order.daily-wrap"; then
  ok "launchd 任务已注册"
else
  fail "launchd 任务未注册"
fi

# ────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  测试结果: $PASS ✅ / $FAIL ❌"
echo "═══════════════════════════════════════════════════════"
[ $FAIL -eq 0 ] && exit 0 || exit 1
