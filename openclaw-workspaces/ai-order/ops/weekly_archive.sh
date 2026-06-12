#!/bin/bash
#
# weekly_archive.sh — 归档 14 天前的 session 日志到 memory/archive/
#
# 功能：
#   1. 查找 memory/ 下 14 天以前的 session 日志（2026-XX-XX.md）
#   2. 移到 memory/archive/YYYY-Www/ 目录（按 ISO 周数命名）
#   3. 如果 archive/ 不存在则创建
#   4. 输出移动了哪些文件
#
# 触发：launchd 每周日 02:00（phase3-maintenance）
#
# 用法：
#   bash ops/weekly_archive.sh              # 正常运行
#   bash ops/weekly_archive.sh --dry-run    # 只打印，不移动

set -e

# 自动检测工作区（优先环境变量，回退到脚本相对路径）
WORKSPACE="${AI_ORDER_WORKSPACE:-$(cd "$(dirname "$0")/.." && pwd)}"
MEMORY_DIR="$WORKSPACE/memory"
ARCHIVE_DIR="$MEMORY_DIR/archive"

DRY_RUN=false
if [[ "$1" == "--dry-run" ]]; then
    DRY_RUN=true
fi

# 14 天前的日期（macOS / Linux 兼容）
if date -j -v-14d +%Y-%m-%d >/dev/null 2>&1; then
    CUTOFF=$(date -j -v-14d +%Y-%m-%d)
else
    CUTOFF=$(date -d "14 days ago" +%Y-%m-%d)
fi

echo "📦 weekly_archive.sh — 归档 $CUTOFF 之前的 session 日志"
echo "   MEMORY_DIR: $MEMORY_DIR"
echo "   ARCHIVE_DIR: $ARCHIVE_DIR"
echo ""

# 确保 archive 目录存在
if [[ ! -d "$ARCHIVE_DIR" ]]; then
    mkdir -p "$ARCHIVE_DIR"
    echo "✅ 创建 archive 目录"
fi

MOVED=0
SKIPPED=0

# 遍历 memory/ 下的日期格式文件
for f in "$MEMORY_DIR"/202[56]-[0-9][0-9]-[0-9][0-9]*.md; do
    [[ -f "$f" ]] || continue

    filename=$(basename "$f")
    # 提取日期部分（支持 2026-06-08.md 和 2026-06-04-to-07.md）
    file_date="${filename:0:10}"

    # 验证日期格式
    if ! echo "$file_date" | grep -qE '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'; then
        SKIPPED=$((SKIPPED + 1))
        continue
    fi

    # 比较日期
    if [[ "$file_date" < "$CUTOFF" ]]; then
        # 计算 ISO 周数（macOS: -f 必须在输入值前面）
        if date -j -f "%Y-%m-%d" "$file_date" +%G-W%V >/dev/null 2>&1; then
            week_dir=$(date -j -f "%Y-%m-%d" "$file_date" +%G-W%V)
        else
            week_dir=$(date -d "$file_date" +%G-W%V 2>/dev/null || echo "unknown")
        fi

        target_dir="$ARCHIVE_DIR/$week_dir"

        if $DRY_RUN; then
            echo "  [dry-run] $filename → archive/$week_dir/"
        else
            mkdir -p "$target_dir"
            mv "$f" "$target_dir/$filename"
            echo "  ✅ $filename → archive/$week_dir/"
        fi
        MOVED=$((MOVED + 1))
    fi
done

echo ""
echo "📊 结果：移动 $MOVED 个文件，跳过 $SKIPPED 个"
if $DRY_RUN; then
    echo "   （dry-run 模式，未实际移动）"
fi
