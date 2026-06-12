#!/bin/bash
#
# version_check.sh — Skill 启动时自动核对版本号
#
# 检查项：
#   1. VERSION 文件 vs SKILL.md 头 vs CHANGELOG.md 最新条目 vs __init__.py VERSION
#   2. 工作区文件：AGENTS.md / MEMORY.md / TOOLS.md
#   3. 所有版本号必须一致，不一致则非零退出
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
WORKSPACE_DIR="$(cd "$SKILL_DIR/../.." && pwd)"
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
VERSION_CHANGELOG=$(grep -E '^##[[:space:]]+\[?[0-9]+\.[0-9]+(\.[0-9]+)?' "$SKILL_DIR/CHANGELOG.md" | head -1 | sed -E 's/^##[[:space:]]+\[?([0-9]+\.[0-9]+(\.[0-9]+)?)\]?.*$/\1/')
if [ -z "$VERSION_CHANGELOG" ]; then
  echo "❌ CHANGELOG.md 中找不到版本条目（应有 '## [X.Y.Z]'）"
  exit 2
fi

# 4. 读 __init__.py VERSION
if [ ! -f "$SKILL_DIR/__init__.py" ]; then
  echo "❌ __init__.py 不存在: $SKILL_DIR/__init__.py"
  exit 2
fi
VERSION_INIT=$(grep -E 'VERSION[[:space:]]*=[[:space:]]*"[0-9]+\.[0-9]+(\.[0-9]+)?"' "$SKILL_DIR/__init__.py" | head -1 | sed -E 's/.*"([0-9]+\.[0-9]+(\.[0-9]+)?)".*/\1/')
if [ -z "$VERSION_INIT" ]; then
  echo "❌ __init__.py 中找不到 VERSION（应有 'VERSION = "X.Y.Z"'）"
  exit 2
fi

# 5. 读工作区文件版本号
VERSION_AGENTS=""
if [ -f "$WORKSPACE_DIR/AGENTS.md" ]; then
  VERSION_AGENTS=$(grep -Eo 'v[0-9]+\.[0-9]+(\.[0-9]+)?' "$WORKSPACE_DIR/AGENTS.md" | head -1 | sed 's/^v//')
fi

VERSION_MEMORY=""
if [ -f "$WORKSPACE_DIR/MEMORY.md" ]; then
  VERSION_MEMORY=$(grep -Eo 'v[0-9]+\.[0-9]+(\.[0-9]+)?' "$WORKSPACE_DIR/MEMORY.md" | head -1 | sed 's/^v//')
fi

VERSION_TOOLS=""
if [ -f "$WORKSPACE_DIR/TOOLS.md" ]; then
  VERSION_TOOLS=$(grep -Eo 'v[0-9]+\.[0-9]+(\.[0-9]+)?' "$WORKSPACE_DIR/TOOLS.md" | head -1 | sed 's/^v//')
fi

# 6. (可选) git tag
VERSION_GIT=""
if [ -d "$SKILL_DIR/.git" ]; then
  VERSION_GIT=$(cd "$SKILL_DIR" && git describe --tags --abbrev=0 2>/dev/null | sed 's/^v//' || echo "")
fi

# 输出
echo "📋 版本号核对 (skill: $(basename "$SKILL_DIR"))"
echo "  VERSION 文件:        $VERSION_FILE"
echo "  SKILL.md 头:         $VERSION_SKILL"
echo "  CHANGELOG.md 最新:   $VERSION_CHANGELOG"
echo "  __init__.py VERSION: $VERSION_INIT"
[ -n "$VERSION_AGENTS" ] && echo "  AGENTS.md:           $VERSION_AGENTS"
[ -n "$VERSION_MEMORY" ] && echo "  MEMORY.md:           $VERSION_MEMORY"
[ -n "$VERSION_TOOLS" ] && echo "  TOOLS.md:            $VERSION_TOOLS"
[ -n "$VERSION_GIT" ] && echo "  git tag 最新:        $VERSION_GIT"

# 7. 比对
ERRORS=0

if [ "$VERSION_FILE" != "$VERSION_SKILL" ]; then
  echo "❌ VERSION 文件 ($VERSION_FILE) ≠ SKILL.md 头 ($VERSION_SKILL)"
  ERRORS=$((ERRORS+1))
fi

if [ "$VERSION_FILE" != "$VERSION_CHANGELOG" ]; then
  echo "❌ VERSION 文件 ($VERSION_FILE) ≠ CHANGELOG.md 最新 ($VERSION_CHANGELOG)"
  ERRORS=$((ERRORS+1))
fi

if [ "$VERSION_FILE" != "$VERSION_INIT" ]; then
  echo "❌ VERSION 文件 ($VERSION_FILE) ≠ __init__.py VERSION ($VERSION_INIT)"
  ERRORS=$((ERRORS+1))
fi

if [ -n "$VERSION_AGENTS" ] && [ "$VERSION_FILE" != "$VERSION_AGENTS" ]; then
  echo "❌ VERSION 文件 ($VERSION_FILE) ≠ AGENTS.md ($VERSION_AGENTS)"
  ERRORS=$((ERRORS+1))
fi

if [ -n "$VERSION_MEMORY" ] && [ "$VERSION_FILE" != "$VERSION_MEMORY" ]; then
  echo "❌ VERSION 文件 ($VERSION_FILE) ≠ MEMORY.md ($VERSION_MEMORY)"
  ERRORS=$((ERRORS+1))
fi

if [ -n "$VERSION_TOOLS" ] && [ "$VERSION_FILE" != "$VERSION_TOOLS" ]; then
  echo "❌ VERSION 文件 ($VERSION_FILE) ≠ TOOLS.md ($VERSION_TOOLS)"
  ERRORS=$((ERRORS+1))
fi

if [ -n "$VERSION_GIT" ] && [ "$VERSION_FILE" != "$VERSION_GIT" ]; then
  echo "⚠️  VERSION 文件 ($VERSION_FILE) ≠ git tag ($VERSION_GIT)（非阻塞）"
fi

if [ $ERRORS -gt 0 ]; then
  echo ""
  echo "🚫 版本号核对失败，共 $ERRORS 个不一致"
  echo "💡 修复方法："
  echo "   1. 确认实际版本号（建议以 VERSION 文件为准）"
  echo "   2. 更新以下文件："
  echo "      - VERSION"
  echo "      - SKILL.md (Version**: X.Y.Z)"
  echo "      - CHANGELOG.md (## [X.Y.Z])"
  echo "      - __init__.py (VERSION = \"X.Y.Z\")"
  echo "      - AGENTS.md (vX.Y.Z)"
  echo "      - MEMORY.md (vX.Y.Z)"
  echo "      - TOOLS.md (vX.Y.Z)"
  exit 1
fi

echo ""
echo "✅ 版本号核对通过：$VERSION_FILE"
exit 0
