#!/usr/bin/env bash
# =============================================================
# sync_check.sh - 文档与代码同步检查 (2026-06-09 启用)
#
# 用途：扫描可能过时的"host/port/user/password"等配置描述
# 用法: bash scripts/sync_check.sh [工作目录]
# 退出码: 0=干净 / 1=有关键命中 / 2=脚本错误
# =============================================================

set -e

RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

WORKSPACE_ROOT="${1:-$(cd "$(dirname "$0")/../.." && pwd)}"
cd "$WORKSPACE_ROOT"

echo "============================================================"
echo "🔍 Sync Check: 文档与代码同步检查"
echo "============================================================"
echo "工作目录: $WORKSPACE_ROOT"
echo "执行时间: $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo ""

PATTERNS=(
    "localhost"
    "jinqianfei"
    "neondb"
    "npg_"
    "TV\*fB4"
    "904825541@qq.com"
    "summer-lab"
    "agent_order"
    "ep-summer-lab"
)

# =============================================================
# 白名单（按目录/文件模式匹配）
# =============================================================
WHITELIST_PATTERNS=(
    "docs/test_data/测评报告"               # 历史测评快照
    "skills/docs/测评报告"                  # 历史测评快照
    "docs/test_data/re_evaluate_skill"      # 历史测试脚本
    "docs/test_data/evaluate_with_ground_truth.py"  # 历史测试脚本
    "docs/云端部署迁移方案"                  # 已加 disclaimer
    "docs/LLM_PROVIDER_REFACTOR"            # LLM 方案（含 localhost:8000）
    "docs/SKILL_EVALUATION_REPORT"          # 测评报告
    "memory/"                               # 历史记忆
    "backups/"                              # 备份目录
    "output/"                               # 输出文件
    "shareable/skill_order_to_huading_template/learn/ADAPTIVE_LEARNING"  # 含 localhost fallback 示例
    "test_llm_parse.py"                     # 临时测试脚本
    "test_order9_e2e.py"                    # 临时测试脚本
)

# 文件后缀白名单
WHITELIST_SUFFIXES=(
    ".zip"
    ".bak"
    ".tmp"
    ".backup"
    ".swp"
)

# 单行白名单 (grep -F 匹配)
WHITELIST_GREP=(
    "/Users/jinqianfei/openclaw-workspaces"  # 路径里的 jinqianfei 是合法的
    "AGENTHUB_DB_CJYS0MSC4X8S"               # RDS host 描述（合法）
)

# =============================================================
# 扫所有 .md / .yaml / .yml / .py
# =============================================================
TARGET_FILES=$(find . \
    -type d \( -name .git -o -name __pycache__ -o -name node_modules -o -name .venv -o -name .openclaw \) -prune -o \
    -type f \( -name "*.md" -o -name "*.yaml" -o -name "*.yml" -o -name "*.py" \) -print 2>/dev/null | \
    sort)

FILE_COUNT=$(echo "$TARGET_FILES" | grep -c . 2>/dev/null || echo 0)
echo -e "${CYAN}扫描 $FILE_COUNT 个文件${NC}"
echo ""

# =============================================================
# 检查
# =============================================================
TOTAL_HITS=0
CRITICAL_HITS=0
P0_HITS=0
P2_HITS=0

for pattern in "${PATTERNS[@]}"; do
    echo "------------------------------------------------------------"
    echo -e "🔎 Pattern: ${YELLOW}$pattern${NC}"
    echo "------------------------------------------------------------"

    HITS=$(echo "$TARGET_FILES" | xargs grep -l "$pattern" 2>/dev/null | sort -u || true)
    if [ -z "$HITS" ]; then
        echo -e "  ${GREEN}✅ 0 hits${NC}"
        echo ""
        continue
    fi

    # 应用白名单
    EFFECTIVE_FILES="$HITS"
    WHITELISTED_FILES=""

    for wl in "${WHITELIST_PATTERNS[@]}"; do
        WM=$(echo "$EFFECTIVE_FILES" | grep -F "$wl" 2>/dev/null || true)
        if [ -n "$WM" ]; then
            WHITELISTED_FILES+="$WM"$'\n'
            EFFECTIVE_FILES=$(echo "$EFFECTIVE_FILES" | grep -v -F "$wl" 2>/dev/null || true)
        fi
    done

    for suffix in "${WHITELIST_SUFFIXES[@]}"; do
        WM=$(echo "$EFFECTIVE_FILES" | grep -F "$suffix" 2>/dev/null || true)
        if [ -n "$WM" ]; then
            WHITELISTED_FILES+="$WM"$'\n'
            EFFECTIVE_FILES=$(echo "$EFFECTIVE_FILES" | grep -v -F "$suffix" 2>/dev/null || true)
        fi
    done

    # 单行白名单需要 grep 内容
    if [ -n "$EFFECTIVE_FILES" ]; then
        for sg in "${WHITELIST_GREP[@]}"; do
            # 找出 EFFECTIVE_FILES 中所有行都只匹配白名单 grep 的文件
            ONLY_WL=$(echo "$EFFECTIVE_FILES" | while read f; do
                [ -z "$f" ] && continue
                # 看这个文件里 pattern 的所有命中是否都包含白名单 grep
                FILE_HITS=$(grep -n "$pattern" "$f" 2>/dev/null || true)
                NON_WL_HITS=$(echo "$FILE_HITS" | grep -v -F "$sg" 2>/dev/null || true)
                if [ -z "$NON_WL_HITS" ]; then
                    echo "$f"
                fi
            done)
            if [ -n "$ONLY_WL" ]; then
                WHITELISTED_FILES+="$ONLY_WL"$'\n'
                EFFECTIVE_FILES=$(echo "$EFFECTIVE_FILES" | grep -v -F -f <(echo "$ONLY_WL") 2>/dev/null || true)
            fi
        done
    fi

    # 统计
    TOTAL_FILE_COUNT=0
    [ -n "$HITS" ] && TOTAL_FILE_COUNT=$(echo "$HITS" | grep -c . 2>/dev/null) && [ -z "$TOTAL_FILE_COUNT" ] && TOTAL_FILE_COUNT=0
    WL_FILE_COUNT=0
    [ -n "$WHITELISTED_FILES" ] && WL_FILE_COUNT=$(echo "$WHITELISTED_FILES" | grep -c . 2>/dev/null) && [ -z "$WL_FILE_COUNT" ] && WL_FILE_COUNT=0
    EF_FILE_COUNT=0
    [ -n "$EFFECTIVE_FILES" ] && EF_FILE_COUNT=$(echo "$EFFECTIVE_FILES" | grep -c . 2>/dev/null) && [ -z "$EF_FILE_COUNT" ] && EF_FILE_COUNT=0

    TOTAL_HITS=$((TOTAL_HITS + TOTAL_FILE_COUNT))
    P2_HITS=$((P2_HITS + WL_FILE_COUNT))
    P0_HITS=$((P0_HITS + EF_FILE_COUNT))

    if [[ "$pattern" =~ (localhost|jinqianfei|neondb|npg_|TV\*fB4|904825541|summer-lab|ep-summer-lab) ]]; then
        CRITICAL_HITS=$((CRITICAL_HITS + EF_FILE_COUNT))
    fi

    if [ "$EF_FILE_COUNT" -gt 0 ]; then
        echo -e "  ${RED}🔴 有效命中 ($EF_FILE_COUNT 个文件):${NC}"
        echo "$EFFECTIVE_FILES" | sed 's/^/    /'
    fi
    if [ "$WL_FILE_COUNT" -gt 0 ]; then
        echo -e "  ${GREEN}⚪ 已白名单 ($WL_FILE_COUNT 个文件)${NC}"
    fi
    echo ""
done

echo "============================================================"
echo "📊 总结"
echo "============================================================"
echo -e "总命中文件数: $TOTAL_HITS"
echo -e "  P0 有效命中 (需清理): ${RED}$P0_HITS${NC}"
echo -e "  P2 白名单放过:         ${GREEN}$P2_HITS${NC}"
echo -e "  关键命中数 (CRITICAL): ${RED}$CRITICAL_HITS${NC}"
echo ""

if [ "$CRITICAL_HITS" -gt 0 ]; then
    echo -e "${YELLOW}⚠️  建议：手动 review 上面的 P0 命中行，按以下优先级清理：${NC}"
    echo "  P0: 当前生效的文档 (IDENTITY/SOUL/USER/SKILL.md 等)"
    echo "  P1: 引用了过期配置的代码 (db_config 硬编码)"
    echo "  P2: 历史报告/计划/记忆 (可保留但加 disclaimer)"
    echo ""
    echo -e "${RED}❌ 同步检查未通过（请修复后重新提交）${NC}"
    exit 1
else
    echo -e "${GREEN}✅ 文档与代码已同步${NC}"
    exit 0
fi
