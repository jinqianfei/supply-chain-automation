#!/bin/bash
# auto_git_skill.sh - 当 skill 文件变化时自动 git 提交
# 用法: ./auto_git_skill.sh [skill_path]
#
# 推荐: 一直运行在后台
#   ./auto_git_skill.sh ~/openclaw-workspaces/ai-order/skills/skill_order_to_huading_template/
#
# 或用 launchd 持久运行（见 SKILL.md 配置）

SKILL_PATH="${1:-$HOME/openclaw-workspaces/ai-order/skills/skill_order_to_huading_template}"
REPO_PATH="$HOME/openclaw-workspaces/ai-order"
LOG_FILE="/tmp/auto_git_skill.log"

echo "[$(date)] 自动 git 监控已启动: $SKILL_PATH" >> "$LOG_FILE"

# 方法1: 用 fswatch（推荐，已安装）
if command -v fswatch &>/dev/null; then
    fswatch -r "$SKILL_PATH" "$REPO_PATH/SKILL.md" "$REPO_PATH/TOOLS.md" 2>/dev/null | while read -r event; do
        FILE=$(echo "$event" | grep -o '[^/]*$')
        echo "[$(date)] 检测到变化: $event" >> "$LOG_FILE"
        cd "$REPO_PATH" || exit
        git add "skills/skill_order_to_huading_template/" "SKILL.md" "TOOLS.md" 2>/dev/null
        if git diff --cached --quiet 2>/dev/null; then
            echo "[$(date)] 无新变化" >> "$LOG_FILE"
        else
            TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
            git commit -m "auto: skill 更新 $TIMESTAMP" 2>/dev/null
            echo "[$(date)] 已自动提交" >> "$LOG_FILE"
            # 尝试推送到 github
            git push github main --quiet 2>/dev/null &
            echo "[$(date)] 已在后台推送" >> "$LOG_FILE"
        fi
    done

# 方法2: 用 stat 轮询（无 fswatch 时）
else
    echo "[$(date)] fswatch 未安装，使用 stat 轮询模式（每30秒）" >> "$LOG_FILE"
    LAST_CHECK=0
    while true; do
        CURRENT=$(find "$SKILL_PATH" -type f -name '*.py' -o -name '*.md' -o -name '*.yaml' 2>/dev/null | xargs stat -f %m 2>/dev/null | sort -n | tail -1)
        if [ "$CURRENT" != "$LAST_CHECK" ] && [ -n "$CURRENT" ]; then
            if [ "$LAST_CHECK" != "0" ] && [ "$CURRENT" != "$LAST_CHECK" ]; then
                echo "[$(date)] 检测到文件变化" >> "$LOG_FILE"
                cd "$REPO_PATH" || exit
                git add "skills/skill_order_to_huading_template/" 2>/dev/null
                if git diff --cached --quiet 2>/dev/null; then
                    echo "[$(date)] 无新变化" >> "$LOG_FILE"
                else
                    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
                    git commit -m "auto: skill 更新 $TIMESTAMP" 2>/dev/null
                    echo "[$(date)] 已自动提交" >> "$LOG_FILE"
                    git push github main --quiet 2>/dev/null &
                fi
            fi
            LAST_CHECK=$CURRENT
        fi
        sleep 30
    done
fi
