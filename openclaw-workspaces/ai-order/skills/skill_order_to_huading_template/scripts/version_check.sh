#!/bin/bash
#
# version_check.sh — Skill 启动时自动核对版本号
#
# 检查项：
#   1. VERSION 文件 vs SKILL.md 头 vs CHANGELOG.md 最新条目
#   2. 三个数字必须一致，不一致则非零退出
#
# 用法：
#   bash scripts/version_check.sh            # 检查当前 skill
#   bash scripts/version_check.sh --strict   # 严格模式，CHANGELOG 未更新也算错
#
# 退出码：
#   0 = 全部一致
#   1 = 有不一致
#   2 = 文件缺失

set -e

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STRICT=false
[ "$1" == "--strict" ] && STRICT=true

# 1. 读 VERSION 文件
if [ ! -f "$SKILL_DIR/VERSION" ]; then
  echo "❌ VERSION 文件不存在: $SKILL_DIR/VERSION"
  exit 2
fi
VERSION_FILE=$(cat "$SKILL_DIR/VERSION" | tr -d '[:space:]')

# 2. 读 SKILL.md 头（搜 "Version**: X.Y.Z" 或 "Version**: X.Y"，兼容 BSD grep）
if [ ! -f "$SKILL_DIR/SKILL.md" ]; then
  echo "❌ SKILL.md 不存在: $SKILL_DIR/SKILL.md"
  exit 2
fi
VERSION_SKILL=$(grep -Eo 'Version\*\*[[:space:]]*:[[:space:]]*[0-9]+\.[0-9]+(\.[0-9]+)?' "$SKILL_DIR/SKILL.md" | head -1 | sed -E 's/.*:[[:space:]]*([0-9]+\.[0-9]+(\.[0-9]+)?).*/\1/')
if [ -z "$VERSION_SKILL" ]; then
  echo "❌ SKILL.md 中找不到版本号（应包含 'Version**: X.Y.Z'）"
  exit 2
fi

# 3. 读 CHANGELOG.md 最新已发布版本（兼容 BSD grep）
if [ ! -f "$SKILL_DIR/CHANGELOG.md" ]; then
  echo "❌ CHANGELOG.md 不存在: $SKILL_DIR/CHANGELOG.md"
  exit 2
fi
VERSION_CHANGELOG=$(grep -E '^##[[:space:]]+\[?[0-9]+\.[0-9]+(\.[0-9]+)?' "$SKILL_DIR/CHANGELOG.md" | head -1 | sed -E 's/.*\[?([0-9]+\.[0-9]+(\.[0-9]+)?).*/\1/')
if [ -z "$VERSION_CHANGELOG" ]; then
  echo "❌ CHANGELOG.md 中找不到版本条目（应有 '## [X.Y.Z]'）"
  exit 2
fi

# 4. (可选) git tag
VERSION_GIT=""
if [ -d "$SKILL_DIR/.git" ]; then
  VERSION_GIT=$(cd "$SKILL_DIR" && git describe --tags --abbrev=0 2>/dev/null | sed 's/^v//' || echo "")
fi

# 输出
echo "📋 版本号核对 (skill: $(basename "$SKILL_DIR"))"
echo "  VERSION 文件:        $VERSION_FILE"
echo "  SKILL.md 头:         $VERSION_SKILL"
echo "  CHANGELOG.md 最新:   $VERSION_CHANGELOG"
[ -n "$VERSION_GIT" ] && echo "  git tag 最新:        $VERSION_GIT"

# 5. 比对
ERRORS=0

if [ "$VERSION_FILE" != "$VERSION_SKILL" ]; then
  echo "❌ VERSION 文件 ($VERSION_FILE) ≠ SKILL.md 头 ($VERSION_SKILL)"
  ERRORS=$((ERRORS+1))
fi

if [ "$VERSION_FILE" != "$VERSION_CHANGELOG" ]; then
  echo "❌ VERSION 文件 ($VERSION_FILE) ≠ CHANGELOG.md 最新 ($VERSION_CHANGELOG)"
  ERRORS=$((ERRORS+1))
fi

if [ -n "$VERSION_GIT" ] && [ "$VERSION_FILE" != "$VERSION_GIT" ]; then
  echo "⚠️  VERSION 文件 ($VERSION_FILE) ≠ git tag ($VERSION_GIT)（非阻塞）"
fi

if [ $ERRORS -gt 0 ]; then
  echo ""
  echo "🚫 版本号核对失败，共 $ERRORS 个不一致"
  echo "💡 修复方法："
  echo "   1. 确认实际版本号（建议以 SKILL.md 头为准，因为是文档声明）"
  echo "   2. 更新 VERSION 文件：echo 'X.Y.Z' > VERSION"
  echo "   3. 更新 CHANGELOG.md 加新条目"
  exit 1
fi

echo ""
echo "✅ 版本号核对通过：$VERSION_FILE"
exit 0
