#!/bin/bash
#
# phase3_maintenance.sh — 每周日凌晨 Phase 3 维护（智能分析）
#
# 执行内容：
#   1. memory_search 索引重建（memory_system/scripts/reindex.py）
#   2. MEMORY.md 自动提取（memory_system/scripts/extract_memory.py --apply）
#   3. 4W 质量检查（memory_system/scripts/check_quality.py --strict）
#
# 触发：launchd 每周日 03:00
#   0 3 * * 0 $WORKSPACE/ops/phase3_maintenance.sh
#
# 用法：
#   bash ops/phase3_maintenance.sh          # 跑全套
#   bash ops/phase3_maintenance.sh --skip-reindex  # 跳过 reindex
#   bash ops/phase3_maintenance.sh --dry-run      # 不写任何文件

set -e

WORKSPACE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$WORKSPACE/memory_system/scripts"

SKIP_REINDEX=false
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --skip-reindex) SKIP_REINDEX=true; shift;;
    --dry-run) DRY_RUN=true; shift;;
    *) echo "未知参数: $1"; exit 1;;
  esac
done

echo "═══════════════════════════════════════════════════════"
echo "  AI建单助手 — Phase 3 周维护（$(date '+%Y-%m-%d %H:%M:%S')）"
echo "═══════════════════════════════════════════════════════"
echo ""

# Step 1: 重建 memory_search 索引
if [ "$SKIP_REINDEX" = false ]; then
  echo "▶ Step 1: 重建 memory_search 索引"
  if [ "$DRY_RUN" = true ]; then
    echo "  (dry-run 跳过)"
  else
    python3 "$SCRIPTS/reindex.py" 2>&1 | tail -5
  fi
  echo ""
fi

# Step 2: MEMORY.md 自动提取
echo "▶ Step 2: MEMORY.md 自动提取"
if [ "$DRY_RUN" = true ]; then
  echo "  (dry-run: 只显示，不写入)"
  python3 "$SCRIPTS/extract_memory.py" 2>&1 | tail -10
else
  python3 "$SCRIPTS/extract_memory.py" --apply 2>&1 | tail -10
fi
echo ""

# Step 3: 4W 质量检查（strict 模式）
echo "▶ Step 3: 4W 质量检查"
python3 "$SCRIPTS/check_quality.py" --strict 2>&1 | tail -10
QUALITY_EXIT=$?
echo ""

echo "═══════════════════════════════════════════════════════"
echo "  ✅ Phase 3 周维护完成"
echo "═══════════════════════════════════════════════════════"

# quality < 0.5 退出非零（让 launchd 知道有警告）
exit $QUALITY_EXIT
