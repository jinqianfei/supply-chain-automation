#!/usr/bin/env bash
# =============================================================
# sync_check.sh - 文档与代码同步检查 (2026-06-09 启用)
#
# 用途：扫描可能过时的"host/port/user/password"等配置描述
# 用法: bash scripts/sync_check.sh [工作目录]
# 退出码: 0=干净 / 1=有关键命中 / 2=脚本错误
#
# 设计原则：
# 1. 跳过"合规 fallback"模式（如 os.getenv("DB_HOST", "localhost")）
# 2. 跳过"路径里的 jinqianfei"（合法用户路径）
# 3. 跳过白名单目录（历史快照/其他 skill/备份等）
# 4. 关键命中数 > 0 时返回非零
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
# 白名单
# =============================================================
WHITELIST_PATHS=(
    "docs/test_data/测评报告"               # 历史测评快照
    "skills/docs/测评报告"                  # 历史测评快照
    "docs/test_data/re_evaluate_skill"      # 历史测试脚本
    "docs/test_data/evaluate_with_ground_truth.py"  # 历史测试脚本
    "docs/云端部署迁移方案"                  # 已加 disclaimer
    "docs/LLM_PROVIDER_REFACTOR"            # LLM 方案（含 localhost:8000）
    "docs/SKILL_EVALUATION_REPORT"          # 测评报告（v5.8 历史快照）
    "SKILL_EVALUATION_REPORT"               # 顶层测评报告（v5.8 历史快照）
    "memory/"                               # 历史记忆
    "backups/"                              # 备份目录
    "output/"                               # 输出文件
    "shareable/skill_order_to_huading_template/learn/ADAPTIVE_LEARNING"  # 含 localhost fallback 示例
    "test_llm_parse.py"                     # 临时测试脚本
    "test_order9_e2e.py"                    # 临时测试脚本
    # 其他 skill（不在本次任务范围，后续单独处理）
    "skills/skill_openclaw_test/"           # 测试 skill
    "skills/skill_openclaw_deploy/"         # 部署 skill
    "skills/skill_ops_monitor/"             # 监控 skill
    "skills/skill_operation_monitor/"       # 监控 skill
    "skills/skill_skill_monitor/"           # 监控 skill
    "skills/skill_openclaw_deploy/SKILL.md.*localhost:18789"  # EC2 端口描述
)

WHITELIST_SUFFIXES=(
    ".zip"
    ".bak"
    ".tmp"
    ".backup"
    ".swp"
)

# 单行白名单（这一行如果只匹配这个字符串，就跳过）
# 用于"路径里出现 jinqianfei"等合法场景
WHITELIST_LINE_PATTERNS=(
    "os.getenv(\"DB_HOST\", \"localhost\")"        # 合规 env fallback
    "os.getenv(\"DB_PORT\", \"5432\")"            # 合规 env fallback
    "os.getenv(\"DB_NAME\", \"neo\")"             # 合规 env fallback
    "os.getenv(\"DB_USER\""                        # 合规 env fallback
    "os.getenv(\"DB_PASSWORD\""                   # 合规 env fallback
    "$HOME/openclaw-workspaces"                    # 当前用户合法路径（跨机器可移植）
    "$HOME/Downloads"                              # 当前用户合法路径
    "$HOME/.openclaw"                              # 当前用户合法路径
    "localhost:18789"                              # EC2 端口描述
    "localhost:3000"                              # 本地服务
    "localhost:8000"                              # 本地 LLM
    "localhost:6379"                              # 本地 Redis
    "localhost:11434"                             # 本地 Ollama
    "ai-order 不是独立仓库，git 根是"             # MEMORY.md 事故描述
    "Neon 账号"                                    # MEMORY.md 事故描述
    "Neon 项目"                                    # MEMORY.md 事故描述
    "历史泄露的"                                  # MEMORY.md 事故描述
    "之前混合描述 RDS"                            # MEMORY.md 事故描述
    "Databases: PostgreSQL 18"                    # 系统信息
    "2e03f2c auto: skill 更新"                    # 正常 commit message
)

# 固定字符串白名单（处理括号等 ERE 特殊字符）
WHITELIST_LINE_FPATTERNS=(
    'os.getenv("DB_HOST", "localhost")'           # 合规 env fallback
    'os.getenv("DB_HOST", "your_db_host")'        # 合规 env fallback
    'os.getenv("DB_PORT", "5432")'                # 合规 env fallback
    'os.getenv("DB_NAME", "neo")'                 # 合规 env fallback
    'os.getenv("DB_USER", "your_username")'       # 合规 env fallback
    'os.getenv("DB_USER", "your_db_host")'        # 合规 env fallback
    'os.getenv("DB_USER"'                         # 合规 env fallback (部分匹配)
    'os.getenv("DB_PASSWORD"'                     # 合规 env fallback (部分匹配)
    'os.environ.get("DB_HOST", "localhost")'       # 合规 env fallback
    'os.environ.get("DB_PORT"'                    # 合规 env fallback
    'os.environ.get("DB_USER"'                    # 合规 env fallback
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

    # 用 grep -n 拿所有命中的 file:line:content
    HITS=$(echo "$TARGET_FILES" | xargs grep -n "$pattern" 2>/dev/null | sort || true)
    if [ -z "$HITS" ]; then
        echo -e "  ${GREEN}✅ 0 hits${NC}"
        echo ""
        continue
    fi

    # 应用路径白名单
    FILTERED_HITS="$HITS"
    WHITELISTED_LINES=""
    for wl in "${WHITELIST_PATHS[@]}"; do
        # wl 可能是 "path/" 或 "path.*pattern"（后者是行级匹配）
        if [[ "$wl" == *"*"* ]]; then
            # 行级匹配
            wl_path="${wl%.*}"
            wl_line="${wl#*.}"
            WM=$(echo "$FILTERED_HITS" | grep -E "^\\./${wl_path}/.*${wl_line}" 2>/dev/null || true)
            if [ -n "$WM" ]; then
                WHITELISTED_LINES+="$WM"$'\n'
                FILTERED_HITS=$(echo "$FILTERED_HITS" | grep -v -E "^\\./${wl_path}/.*${wl_line}" 2>/dev/null || true)
            fi
        else
            WM=$(echo "$FILTERED_HITS" | grep -E "^\\./${wl#/\\./}" 2>/dev/null || true)
            if [ -n "$WM" ]; then
                WHITELISTED_LINES+="$WM"$'\n'
                FILTERED_HITS=$(echo "$FILTERED_HITS" | grep -v -E "^\\./${wl#/\\./}" 2>/dev/null || true)
            fi
        fi
    done

    # 应用后缀白名单
    for suffix in "${WHITELIST_SUFFIXES[@]}"; do
        WM=$(echo "$FILTERED_HITS" | grep -E "${suffix}:" 2>/dev/null || true)
        if [ -n "$WM" ]; then
            WHITELISTED_LINES+="$WM"$'\n'
            FILTERED_HITS=$(echo "$FILTERED_HITS" | grep -v -E "${suffix}:" 2>/dev/null || true)
        fi
    done

        # 应用单行白名单 - 正则（grep -E）
    for lp in "${WHITELIST_LINE_PATTERNS[@]}"; do
        WM=$(echo "$FILTERED_HITS" | grep -E "$lp" 2>/dev/null || true)
        if [ -n "$WM" ]; then
            WHITELISTED_LINES+="$WM"$'\n'
            FILTERED_HITS=$(echo "$FILTERED_HITS" | grep -v -E "$lp" 2>/dev/null || true)
        fi
    done

    # 应用单行白名单 - 固定字符串（grep -F，处理括号等 ERE 特殊字符）
    for lp in "${WHITELIST_LINE_FPATTERNS[@]}"; do
        WM=$(echo "$FILTERED_HITS" | grep -F "$lp" 2>/dev/null || true)
        if [ -n "$WM" ]; then
            WHITELISTED_LINES+="$WM"$'\n'
            FILTERED_HITS=$(echo "$FILTERED_HITS" | grep -v -F "$lp" 2>/dev/null || true)
        fi
    done

    # 统计
    HIT_COUNT=0
    [ -n "$HITS" ] && HIT_COUNT=$(echo "$HITS" | grep -c . 2>/dev/null) && [ -z "$HIT_COUNT" ] && HIT_COUNT=0
    WL_COUNT=0
    [ -n "$WHITELISTED_LINES" ] && WL_COUNT=$(echo "$WHITELISTED_LINES" | grep -c . 2>/dev/null) && [ -z "$WL_COUNT" ] && WL_COUNT=0
    EF_COUNT=0
    [ -n "$FILTERED_HITS" ] && EF_COUNT=$(echo "$FILTERED_HITS" | grep -c . 2>/dev/null) && [ -z "$EF_COUNT" ] && EF_COUNT=0

    TOTAL_HITS=$((TOTAL_HITS + HIT_COUNT))
    P2_HITS=$((P2_HITS + WL_COUNT))
    P0_HITS=$((P0_HITS + EF_COUNT))

    if [[ "$pattern" =~ (localhost|jinqianfei|neondb|npg_|TV\*fB4|904825541|summer-lab|ep-summer-lab) ]]; then
        CRITICAL_HITS=$((CRITICAL_HITS + EF_COUNT))
    fi

    if [ "$EF_COUNT" -gt 0 ]; then
        echo -e "  ${RED}🔴 有效命中 ($EF_COUNT 行):${NC}"
        echo "$FILTERED_HITS" | head -30 | sed 's/^/    /'
    fi
    if [ "$WL_COUNT" -gt 0 ]; then
        echo -e "  ${GREEN}⚪ 已白名单 ($WL_COUNT 行)${NC}"
    fi
    echo ""
done

echo "============================================================"
echo "📊 总结"
echo "============================================================"
echo -e "总命中行数: $TOTAL_HITS"
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
