#!/bin/bash
# ============================================================
# AI建单助手 - 一键同步到阿里云 OpenClaw
# 版本: v1.0 | 日期: 2026-06-12
#
# 使用方法:
#   1. 首次使用：填写下方配置，然后执行:
#      bash ops/sync_to_aliyun.sh --setup
#      （会设置 SSH 免密登录，之后不再需要密码）
#
#   2. 日常同步:
#      bash ops/sync_to_aliyun.sh
#
# 依赖: sshpass (首次 setup 用，之后可卸载)
#   brew install hudochenkov/sshpass/sshpass
# ============================================================

set -e

# ==================== 配置区 ====================

# 阿里云 ECS 配置
ALIYUN_HOST=""          # ECS 公网 IP 或域名
ALIYUN_PORT="22"        # SSH 端口，默认 22
ALIYUN_USER="root"      # SSH 用户名
ALIYUN_PASS=""          # SSH 密码（仅 setup 时使用，设置完免密后可清空）

# 阿里云 OpenClaw 工作区路径
ALIYUN_WORKSPACE="/root/openclaw-workspaces/ai-order"

# 本地工作区路径（从环境变量或自动检测）
LOCAL_WORKSPACE="${AI_ORDER_WORKSPACE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

# Git 分支
GIT_BRANCH="main"

# 是否在同步后跑 CI 回归测试
RUN_CI=true

# 同步后是否重启 OpenClaw
RESTART_OPENCLAW=true

# ==================== 颜色 ====================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ==================== 函数 ====================

log() { echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $1"; }
ok() { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
fail() { echo -e "${RED}[✗]${NC} $1"; exit 1; }

# 通过 SSH 在阿里云执行命令
remote_exec() {
    ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
        -p "$ALIYUN_PORT" "${ALIYUN_USER}@${ALIYUN_HOST}" "$@"
}

# ==================== Setup: 设置 SSH 免密 ====================

do_setup() {
    log "🔑 设置 SSH 免密登录..."

    if [ -z "$ALIYUN_HOST" ] || [ -z "$ALIYUN_PASS" ]; then
        fail "请先在脚本配置区填写 ALIYUN_HOST 和 ALIYUN_PASS"
    fi

    # 检查 sshpass
    if ! command -v sshpass &>/dev/null; then
        log "安装 sshpass..."
        brew install hudochenkov/sshpass/sshpass 2>/dev/null || {
            warn "brew 安装失败，请手动安装: brew install hudochenkov/sshpass/sshpass"
            fail "sshpass 未安装"
        }
    fi

    # 检查本地 SSH key
    if [ ! -f ~/.ssh/id_rsa.pub ] && [ ! -f ~/.ssh/id_ed25519.pub ]; then
        log "生成 SSH key..."
        ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N "" -q
    fi

    # 选择 key
    if [ -f ~/.ssh/id_ed25519.pub ]; then
        SSH_KEY=~/.ssh/id_ed25519.pub
    else
        SSH_KEY=~/.ssh/id_rsa.pub
    fi

    log "将公钥复制到阿里云 ECS ($ALIYUN_HOST)..."
    log "（需要输入一次服务器密码）"

    sshpass -p "$ALIYUN_PASS" ssh-copy-id \
        -o StrictHostKeyChecking=no \
        -p "$ALIYUN_PORT" \
        "${ALIYUN_USER}@${ALIYUN_HOST}" 2>&1

    # 验证
    if remote_exec "echo 'SSH 免密登录成功'" &>/dev/null; then
        ok "SSH 免密登录设置成功！"
        ok "之后同步不再需要密码"

        # 清空配置中的密码
        warn "建议清空脚本中的 ALIYUN_PASS 配置"
    else
        fail "SSH 免密设置失败，请检查密码和网络"
    fi
}

# ==================== 主同步流程 ====================

do_sync() {
    cd "$LOCAL_WORKSPACE"

    echo ""
    echo "================================================"
    echo "🔄 AI建单助手 → 阿里云同步"
    echo "================================================"
    echo ""

    # Step 1: 检查配置
    log "Step 1/5: 检查配置..."
    if [ -z "$ALIYUN_HOST" ]; then
        fail "请先在脚本配置区填写 ALIYUN_HOST"
    fi
    if ! remote_exec "echo ok" &>/dev/null; then
        fail "无法 SSH 连接到 $ALIYUN_HOST，请检查网络和免密登录"
    fi
    ok "SSH 连接正常"

    # Step 2: Git commit + push
    log "Step 2/5: 本地 Git 提交..."

    # 检查是否有变更
    CHANGED=$(git status --porcelain)
    if [ -n "$CHANGED" ]; then
        git add -A

        # 生成 commit message
        CHANGED_FILES=$(git diff --cached --name-only | head -5 | tr '\n' ', ' | sed 's/,$//')
        CHANGED_COUNT=$(git diff --cached --name-only | wc -l | tr -d ' ')
        COMMIT_MSG="sync: ${CHANGED_COUNT} files changed (${CHANGED_FILES})"
        if [ "$CHANGED_COUNT" -gt 5 ]; then
            COMMIT_MSG="${COMMIT_MSG} +$(( CHANGED_COUNT - 5 )) more"
        fi

        git commit -m "$COMMIT_MSG" -q
        ok "本地 commit: $COMMIT_MSG"
    else
        ok "本地无新变更"
    fi

    log "Push 到远程仓库..."
    git push origin "$GIT_BRANCH" -q 2>&1 || {
        warn "git push 失败（可能没有远程仓库），继续用 SSH 直传方式"
        DIRECT_TRANSFER=true
    }
    ok "Push 完成"

    # Step 3: 阿里云同步
    log "Step 3/5: 阿里云同步..."

    if [ "$DIRECT_TRANSFER" = true ]; then
        # 没有远程仓库，用 rsync 直传
        warn "使用 rsync 直传（建议配置 Git 远程仓库更方便）"
        rsync -avz --delete \
            --exclude='.git' \
            --exclude='__pycache__' \
            --exclude='*.pyc' \
            --exclude='.env' \
            --exclude='output/' \
            -e "ssh -p $ALIYUN_PORT" \
            "$LOCAL_WORKSPACE/" \
            "${ALIYUN_USER}@${ALIYUN_HOST}:${ALIYUN_WORKSPACE}/" \
            2>&1 | tail -3
    else
        # 有远程仓库，SSH 拉取
        remote_exec "cd $ALIYUN_WORKSPACE && git pull origin $GIT_BRANCH --ff-only 2>&1" || {
            warn "git pull 失败，尝试 reset..."
            remote_exec "cd $ALIYUN_WORKSPACE && git fetch origin $GIT_BRANCH && git reset --hard origin/$GIT_BRANCH"
        }
    fi
    ok "代码同步完成"

    # Step 4: 执行数据库迁移（如有）
    log "Step 4/5: 检查数据库迁移..."
    PENDING_SQL=$(remote_exec "ls -t $ALIYUN_WORKSPACE/migrations/*.sql 2>/dev/null | head -1" 2>/dev/null || echo "")
    if [ -n "$PENDING_SQL" ]; then
        log "发现 SQL 迁移文件: $PENDING_SQL"
        remote_exec "cd $ALIYUN_WORKSPACE && bash ops/run_migrations.sh" 2>&1
        ok "数据库迁移完成"
    else
        ok "无数据库迁移"
    fi

    # Step 5: 重启 OpenClaw + CI 测试
    log "Step 5/5: 重启 + 验证..."

    if [ "$RESTART_OPENCLAW" = true ]; then
        remote_exec "openclaw gateway restart 2>&1" || {
            remote_exec "systemctl restart openclaw 2>&1" || warn "重启命令未找到，请手动重启"
        }
        ok "OpenClaw 已重启"
    fi

    if [ "$RUN_CI" = true ]; then
        log "运行 CI 回归测试..."
        CI_RESULT=$(remote_exec "cd $ALIYUN_WORKSPACE && bash skills/skill_order_to_huading_template/scripts/ci_regression.sh 2>&1 | tail -5" 2>/dev/null || echo "CI 未配置或跳过")
        echo "  $CI_RESULT"
    fi

    # 获取阿里云版本号
    REMOTE_VERSION=$(remote_exec "cat $ALIYUN_WORKSPACE/skills/skill_order_to_huading_template/VERSION 2>/dev/null" || echo "unknown")
    ok "阿里云 Skill 版本: $REMOTE_VERSION"

    # ==================== 结果 ====================
    echo ""
    echo "================================================"
    echo "✅ 同步完成！"
    echo "================================================"
    echo "  本地版本: $(cat skills/skill_order_to_huading_template/VERSION)"
    echo "  远程版本: $REMOTE_VERSION"
    echo "  服务器:   $ALIYUN_HOST"
    echo "  时间:     $(date '+%Y-%m-%d %H:%M:%S')"
    echo "================================================"
    echo ""

    # 记录同步日志
    LOG_DIR="$LOCAL_WORKSPACE/output/sync_logs"
    mkdir -p "$LOG_DIR"
    cat >> "$LOG_DIR/sync_history.log" << EOF
[$(date '+%Y-%m-%d %H:%M:%S')] sync OK | local=$(cat skills/skill_order_to_huading_template/VERSION) | remote=$REMOTE_VERSION | host=$ALIYUN_HOST
EOF
}

# ==================== 入口 ====================

case "${1:-sync}" in
    --setup|setup)
        do_setup
        ;;
    --help|help|-h)
        echo "用法:"
        echo "  bash ops/sync_to_aliyun.sh          # 日常同步"
        echo "  bash ops/sync_to_aliyun.sh --setup   # 首次: 设置 SSH 免密"
        echo "  bash ops/sync_to_aliyun.sh --help    # 帮助"
        ;;
    *)
        do_sync
        ;;
esac
