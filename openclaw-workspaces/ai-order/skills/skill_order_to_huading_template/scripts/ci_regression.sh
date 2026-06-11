#!/bin/bash
#
# ci_regression.sh — Skill 全量回归 CI 入口
#
# 目的:
#   启动时自动跑全部回归测试,任何失败立即报警并阻止启动
#   v5.13.3 (2026-06-11) 金姐反馈"果糖-"匹配不到 bug 修复后建立
#
# 检查项:
#   1. 版本号一致性 (version_check.sh)
#   2. 门店确认流程 (test_execute_confirmation_flow.py)
#   3. import fallback (test_execute_import_fallback.py)
#   4. Excel 解析 (test_order_parser_excel_header_detail.py)
#   5. 文本解析 (test_order_parser_text_fallback.py)
#   6. SKU 映射器回归 (test_sku_mapper_regression.py)
#   6.5 映射准确率: 门店/货主/单位 (test_mapping_accuracy.py)
#   7. 事件管道 (test_event_pipeline.py)
#
# 用法:
#   bash scripts/ci_regression.sh              # 全量跑
#   bash scripts/ci_regression.sh --no-events   # 跳过事件管道
#   bash scripts/ci_regression.sh --no-sku      # 跳过 SKU 回归
#
# 退出码:
#   0 = 全部通过
#   1 = 有失败
#   2 = 环境问题 (DB 未配置等)
#
# CI 集成:
#   - 启动 hook: 在 start_session / 订单处理前调用
#   - 定时: launchd 每天 10:00 日结时调用 (写进 daily_wrap.sh)
#   - 手动: 修改 _sku_mapper.py 后必跑

set -e

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKSPACE_DIR="$(cd "$SKILL_DIR/../.." && pwd)"

NO_EVENTS=false
NO_SKU=false
[ "$1" == "--no-events" ] && NO_EVENTS=true
[ "$2" == "--no-events" ] && NO_EVENTS=true
[ "$1" == "--no-sku" ] && NO_SKU=true

PASS_COUNT=0
FAIL_COUNT=0

run_step() {
    local name="$1"
    local cmd="$2"
    echo ""
    echo "▶ $name"
    echo "────────────────────────────────────────"
    if eval "$cmd"; then
        echo "✅ $name 通过"
        PASS_COUNT=$((PASS_COUNT + 1))
    else
        echo "❌ $name 失败"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
}

# 1. 版本号核对
run_step "版本号一致性" "bash '$SKILL_DIR/scripts/version_check.sh'"

# 2. 门店确认流程
if [ -f "$SKILL_DIR/scripts/test_execute_confirmation_flow.py" ]; then
    run_step "门店确认流程" \
             "python3 '$SKILL_DIR/scripts/test_execute_confirmation_flow.py'"
fi

# 3. import fallback
if [ -f "$SKILL_DIR/scripts/test_execute_import_fallback.py" ]; then
    run_step "import fallback" \
             "python3 '$SKILL_DIR/scripts/test_execute_import_fallback.py'"
fi

# 4. Excel 解析
if [ -f "$SKILL_DIR/scripts/test_order_parser_excel_header_detail.py" ]; then
    run_step "Excel 解析" \
             "python3 '$SKILL_DIR/scripts/test_order_parser_excel_header_detail.py'"
fi

# 5. 文本解析
if [ -f "$SKILL_DIR/scripts/test_order_parser_text_fallback.py" ]; then
    run_step "文本解析" \
             "python3 '$SKILL_DIR/scripts/test_order_parser_text_fallback.py'"
fi

# 6. SKU 映射器回归
if [ "$NO_SKU" = false ]; then
    run_step "SKU 映射器回归 (v5.13.3+)" \
             "python3 '$SKILL_DIR/scripts/test_sku_mapper_regression.py'"
fi

# 6.5 映射准确率 (门店/货主/单位)
if [ "$NO_SKU" = false ] && [ -f "$SKILL_DIR/scripts/test_mapping_accuracy.py" ]; then
    run_step "映射准确率 (门店/货主/单位)" \
             "python3 '$SKILL_DIR/scripts/test_mapping_accuracy.py'"
fi

# 7. 事件管道
if [ "$NO_EVENTS" = false ] && [ -f "$SKILL_DIR/scripts/test_event_pipeline.py" ]; then
    run_step "事件管道 (Phase 1)" \
             "python3 '$SKILL_DIR/scripts/test_event_pipeline.py'"
fi

# 汇总
echo ""
echo "════════════════════════════════════════"
TOTAL=$((PASS_COUNT + FAIL_COUNT))
echo "CI 回归: $TOTAL 步骤, $PASS_COUNT ✅ 通过, $FAIL_COUNT ❌ 失败"
echo "════════════════════════════════════════"

if [ $FAIL_COUNT -gt 0 ]; then
    echo ""
    echo "🚫 回归测试失败,请修复后再启动"
    exit 1
fi

exit 0