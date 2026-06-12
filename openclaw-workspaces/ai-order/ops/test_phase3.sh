#!/bin/bash
#
# test_phase3.sh — Phase 3 三个智能脚本的端到端测试
#
# 覆盖：
# 1. reindex.py（build / check / query）
# 2. extract_memory.py（生成摘要 / --apply 替换）
# 3. check_quality.py（4W 检查 / 质量分）
# 4. phase3_maintenance.sh（干跑全套）

# 不 set -e：测试要检所有可能退出码

WORKSPACE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$WORKSPACE/memory_system/scripts"

PASS=0
FAIL=0

ok() { echo "  ✅ $1"; PASS=$((PASS+1)); }
fail() { echo "  ❌ $1"; FAIL=$((FAIL+1)); }
sep() { echo ""; echo "─── $1 ───"; }

# ────────────────────────────────────────
sep "Test 1: reindex.py — 重建索引"
OUT=$(python3 "$SCRIPTS/reindex.py" 2>&1)
EC=$?
if [ "$EC" -eq 0 ] && echo "$OUT" | grep -q "索引构建完成"; then
  ok "reindex_memory build 成功"
  FILE_COUNT=$(echo "$OUT" | sed -nE 's/.*索引构建完成：([0-9]+).*/\1/p')
  if [ "$FILE_COUNT" -gt 50 ]; then
    ok "索引了 $FILE_COUNT 个文件（>50）"
  else
    fail "索引文件数偏少：$FILE_COUNT"
  fi
else
  fail "reindex_memory build 失败"
fi

# ────────────────────────────────────────
sep "Test 2: reindex.py — 健康检查"
OUT=$(python3 "$SCRIPTS/reindex.py" --check 2>&1)
EC=$?
if [ "$EC" -eq 0 ] && echo "$OUT" | grep -q "索引健康检查"; then
  ok "reindex_memory --check 成功"
  if echo "$OUT" | grep -q "索引与文件系统一致"; then
    ok "索引一致"
  else
    fail "索引与文件系统不一致"
  fi
else
  fail "reindex_memory --check 失败"
fi

# ────────────────────────────────────────
sep "Test 3: reindex.py — 搜索 version_check"
OUT=$(python3 "$SCRIPTS/reindex.py" --query "version_check" 2>&1)
EC=$?
if [ "$EC" -eq 0 ] && echo "$OUT" | grep -q "version_check.*匹配"; then
  ok "搜索 'version_check' 成功"
  if echo "$OUT" | grep -q "MEMORY_SYSTEM_PLAN"; then
    ok "命中 MEMORY_SYSTEM_PLAN（高相关）"
  else
    fail "没命中关键文件 MEMORY_SYSTEM_PLAN"
  fi
else
  fail "搜索 'version_check' 失败"
fi

# ────────────────────────────────────────
sep "Test 4: reindex.py — 搜索中文"
OUT=$(python3 "$SCRIPTS/reindex.py" --query "断档" 2>&1)
EC=$?
if [ "$EC" -eq 0 ] && echo "$OUT" | grep -q "断档.*匹配"; then
  ok "搜索中文 '断档' 成功"
else
  fail "搜索中文失败"
fi

# ────────────────────────────────────────
sep "Test 5: extract_memory.py — 生成摘要"
OUT=$(python3 "$SCRIPTS/extract_memory.py" 2>&1)
EC=$?
if [ "$EC" -eq 0 ] && echo "$OUT" | grep -q "Session 摘要"; then
  ok "extract_memory 生成摘要成功"
  if echo "$OUT" | grep -q "PENDING.md"; then
    ok "摘要包含 PENDING 追踪"
  else
    fail "摘要缺 PENDING"
  fi
  if echo "$OUT" | grep -q "git log"; then
    ok "摘要包含 git log"
  else
    fail "摘要缺 git log"
  fi
else
  fail "extract_memory 失败"
fi

# ────────────────────────────────────────
sep "Test 6: extract_memory.py --apply 替换 MEMORY.md"
# 备份
cp "$WORKSPACE/MEMORY.md" /tmp/MEMORY.md.test_backup
OUT=$(python3 "$SCRIPTS/extract_memory.py" --apply 2>&1)
EC=$?
if [ "$EC" -eq 0 ]; then
  if grep -q "自动提取摘要" "$WORKSPACE/MEMORY.md"; then
    ok "MEMORY.md 已替换会话摘要"
  else
    fail "MEMORY.md 未替换"
  fi
  # 还原
  cp /tmp/MEMORY.md.test_backup "$WORKSPACE/MEMORY.md"
  ok "已还原 MEMORY.md"
else
  fail "extract_memory --apply 失败：$EC"
fi

# ────────────────────────────────────────
sep "Test 7: check_quality.py — 全量检查"
OUT=$(python3 "$SCRIPTS/check_quality.py" 2>&1)
EC=$?
if [ "$EC" -eq 0 ] && echo "$OUT" | grep -q "统计:"; then
  ok "4W 检查跑通"
  echo "  📊 摘要: $(echo "$OUT" | grep '统计:' | head -1)"
else
  fail "4W 检查失败"
fi

# ────────────────────────────────────────
sep "Test 8: check_quality.py --file 单个文件"
OUT=$(python3 "$SCRIPTS/check_quality.py" --file memory/2026-06-08.md 2>&1)
EC=$?
if [ "$EC" -eq 0 ] && echo "$OUT" | grep -q "2026-06-08.md"; then
  ok "单文件检查成功"
else
  fail "单文件检查失败"
fi

# ────────────────────────────────────────
sep "Test 9: check_quality.py --strict"
OUT=$(python3 "$SCRIPTS/check_quality.py" --strict 2>&1)
EC=$?
if [ "$EC" -eq 0 ] || [ "$EC" -eq 1 ]; then
  ok "--strict 退出码可接受（$EC）"
else
  fail "--strict 退出码异常: $EC"
fi

# ────────────────────────────────────────
sep "Test 10: phase3_maintenance.sh 干跑"
OUT=$(bash "$WORKSPACE/ops/phase3_maintenance.sh" --dry-run 2>&1)
EC=$?
if [ "$EC" -eq 0 ] && echo "$OUT" | grep -q "Phase 3 周维护完成"; then
  ok "phase3_maintenance 干跑成功"
else
  fail "phase3_maintenance 干跑失败：$EC"
fi

# ────────────────────────────────────────
sep "Test 11: launchd phase3 任务已注册"
if launchctl list 2>/dev/null | grep -q "com.ai-order.phase3-maintenance"; then
  ok "phase3 launchd 任务已注册"
else
  fail "phase3 launchd 任务未注册"
fi

# ────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  测试结果: $PASS ✅ / $FAIL ❌"
echo "═══════════════════════════════════════════════════════"
[ $FAIL -eq 0 ] && exit 0 || exit 1
