#!/bin/bash
#
# install_launchd.sh — 安装 ai-order 定时任务（macOS launchd）
#
# 用途：
#   把 launchd/*.plist 安装到 ~/Library/LaunchAgents/
#   安装时自动替换 plist 中的工作区路径为当前机器的实际路径
#
# 用法：
#   bash ops/install_launchd.sh install   # 安装全部
#   bash ops/install_launchd.sh uninstall # 卸载全部
#   bash ops/install_launchd.sh status    # 查看状态
#   bash ops/install_launchd.sh test      # 立即跑一次 daily_wrap.sh

set -e

# 自动检测工作区路径
WORKSPACE="${AI_ORDER_WORKSPACE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
LAUNCHD_DIR="$WORKSPACE/launchd"
PLIST_NAMES=(
  "com.ai-order.daily-wrap.plist"
  "com.ai-order.daily-alias-summary.plist"
  "com.ai-order.phase3-maintenance.plist"
)

# plist 模板中的占位符（安装时替换为实际绝对路径）
PLACEHOLDER="__WORKSPACE__"

install_all() {
  echo "📦 安装 launchd 定时任务"
  echo "   工作区: $WORKSPACE"
  echo ""
  mkdir -p "$HOME/Library/LaunchAgents"

  for PLIST_NAME in "${PLIST_NAMES[@]}"; do
    PLIST_SRC="$LAUNCHD_DIR/$PLIST_NAME"
    PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME"

    if [ ! -f "$PLIST_SRC" ]; then
      echo "  ⚠️  跳过（文件不存在）: $PLIST_SRC"
      continue
    fi

    # 卸载旧的（如果存在）
    launchctl unload "$PLIST_DEST" 2>/dev/null || true

    # 复制并替换路径（用 sed 替换占位符为实际工作区路径）
    if grep -q "$PLACEHOLDER" "$PLIST_SRC"; then
      sed "s|$PLACEHOLDER|$WORKSPACE|g" "$PLIST_SRC" > "$PLIST_DEST"
      echo "  ✅ $PLIST_NAME（路径已替换）"
    else
      cp "$PLIST_SRC" "$PLIST_DEST"
      echo "  ✅ $PLIST_NAME（无需替换）"
    fi

    # 加载
    launchctl load "$PLIST_DEST"
  done

  echo ""
  echo "  已安装并启动:"
  launchctl list | grep ai-order || echo "  (无)"
}

uninstall_all() {
  echo "🗑️  卸载 launchd 定时任务"
  for PLIST_NAME in "${PLIST_NAMES[@]}"; do
    PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME"
    if [ -f "$PLIST_DEST" ]; then
      launchctl unload "$PLIST_DEST" 2>/dev/null || true
      rm "$PLIST_DEST"
      echo "  ✅ 已卸载: $PLIST_NAME"
    else
      echo "  ⚠️  未安装: $PLIST_NAME"
    fi
  done
}

show_status() {
  echo "📋 launchd 状态"
  echo ""
  for PLIST_NAME in "${PLIST_NAMES[@]}"; do
    PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME"
    if [ -f "$PLIST_DEST" ]; then
      echo "  ✅ $PLIST_NAME"
      # 显示实际路径（方便确认替换是否正确）
      grep -o '<string>[^<]*</string>' "$PLIST_DEST" | head -3 | sed 's/^/     /'
    else
      echo "  ❌ $PLIST_NAME（未安装）"
    fi
  done
  echo ""
  echo "  --- launchctl list ---"
  launchctl list | grep ai-order || echo "  (无运行中的任务)"
}

run_test() {
  echo "🧪 立即跑一次 daily_wrap.sh（不等待 10:00）"
  bash "$WORKSPACE/ops/daily_wrap.sh"
}

case "${1:-install}" in
  install)  install_all ;;
  uninstall) uninstall_all ;;
  status)   show_status ;;
  test)     run_test ;;
  *)
    echo "用法: $0 {install|uninstall|status|test}"
    exit 1
    ;;
esac
