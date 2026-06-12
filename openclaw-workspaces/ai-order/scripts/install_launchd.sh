#!/bin/bash
#
# install_launchd.sh — 安装 daily_wrap 定时任务（macOS launchd）
#
# 用途：
#   把 launchd/com.ai-order.daily-wrap.plist 安装到 ~/Library/LaunchAgents/
#   立即生效，每天 10:00 自动跑 daily_wrap.sh
#
# 用法：
#   bash scripts/install_launchd.sh install   # 安装
#   bash scripts/install_launchd.sh uninstall # 卸载
#   bash scripts/install_launchd.sh status    # 查看状态
#   bash scripts/install_launchd.sh test      # 立即跑一次（不等待 10:00）

set -e

PLIST_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/launchd/com.ai-order.daily-wrap.plist"
PLIST_NAME="com.ai-order.daily-wrap.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME"

case "${1:-install}" in
  install)
    echo "📦 安装 launchd 任务"
    mkdir -p "$HOME/Library/LaunchAgents"
    cp "$PLIST_SRC" "$PLIST_DEST"
    launchctl unload "$PLIST_DEST" 2>/dev/null || true
    launchctl load "$PLIST_DEST"
    echo "  ✅ 已安装并启动: $PLIST_DEST"
    echo "  ⏰ 每天 10:00 自动跑 daily_wrap.sh（总结昨天数据）"
    launchctl list | grep ai-order || true
    ;;

  uninstall)
    echo "🗑️  卸载 launchd 任务"
    if [ -f "$PLIST_DEST" ]; then
      launchctl unload "$PLIST_DEST" 2>/dev/null || true
      rm "$PLIST_DEST"
      echo "  ✅ 已卸载: $PLIST_DEST"
    else
      echo "  ⚠️  未安装"
    fi
    ;;

  status)
    echo "📋 状态"
    if [ -f "$PLIST_DEST" ]; then
      echo "  ✅ 已安装: $PLIST_DEST"
      echo "  --- launchctl list ---"
      launchctl list | grep ai-order || echo "  (无)"
      echo "  --- 日志 ---"
      echo "  stdout: /tmp/ai-order.daily-wrap.out.log"
      echo "  stderr: /tmp/ai-order.daily-wrap.err.log"
    else
      echo "  ❌ 未安装"
    fi
    ;;

  test)
    echo "🧪 立即跑一次 daily_wrap.sh（不等待 10:00）"
    bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/daily_wrap.sh"
    ;;

  *)
    echo "用法: $0 {install|uninstall|status|test}"
    exit 1
    ;;
esac
