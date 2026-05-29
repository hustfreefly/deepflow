#!/bin/bash
# DeepFlow V4.0 安全清理脚本
# 执行前已创建双重备份：
#   1. ~/Desktop/DeepFlow_Backup_20260423_134030
#   2. ~/.openclaw/DeepFlow_Backup_20260423_134623
#
# 使用方法：
#   bash cleanup_plan.sh --dry-run    # 先预览，不删除
#   bash cleanup_plan.sh --execute    # 确认后执行

set -euo pipefail

DEEPFLOW_DIR="/Users/allen/.openclaw/workspace/.deepflow"
DRY_RUN=true

# 解析参数
case "${1:-}" in
    --execute)
        DRY_RUN=false
        echo "⚠️  执行模式：将真正删除文件！"
        read -p "确认执行？输入 'yes': " confirm
        if [[ "$confirm" != "yes" ]]; then
            echo "已取消"
            exit 0
        fi
        ;;
    *)
        echo "🔍 预览模式：只显示将要删除的文件，不真正删除"
        echo "   使用 --execute 参数执行真正清理"
        echo ""
        ;;
esac

delete_item() {
    local path="$1"
    if [[ "$DRY_RUN" == true ]]; then
        echo "  [预览] 将删除: $path"
    else
        rm -rf "$path"
        echo "  ✅ 已删除: $path"
    fi
}

echo "=========================================="
echo "DeepFlow 清理计划"
echo "=========================================="
echo ""

# ========================================
# 第1步：清理 blackboard（测试结果）
# ========================================
echo "【第1步】清理 blackboard 测试结果"
echo "  原因: 每次运行都会重新生成，不需要版本控制"
echo "  大小: ~4.9MB"
echo ""

if [[ -d "$DEEPFLOW_DIR/blackboard" ]]; then
    for item in "$DEEPFLOW_DIR/blackboard"/*; do
        if [[ -e "$item" ]]; then
            delete_item "$item"
        fi
    done
fi

echo ""

# ========================================
# 第2步：清理 Python 缓存
# ========================================
echo "【第2步】清理 Python 缓存文件"
echo "  原因: 自动重建，不需要提交"
echo ""

find "$DEEPFLOW_DIR" -type d -name "__pycache__" | while read -r dir; do
    delete_item "$dir"
done

find "$DEEPFLOW_DIR" -name "*.pyc" | while read -r file; do
    delete_item "$file"
done

find "$DEEPFLOW_DIR" -name "*.pyo" | while read -r file; do
    delete_item "$file"
done

echo ""

# ========================================
# 第3步：清理系统文件
# ========================================
echo "【第3步】清理系统文件 (.DS_Store)"
echo ""

find "$DEEPFLOW_DIR" -name ".DS_Store" | while read -r file; do
    delete_item "$file"
done

echo ""

# ========================================
# 第4步：清理测试缓存
# ========================================
echo "【第4步】清理 pytest 缓存"
echo ""

if [[ -d "$DEEPFLOW_DIR/.pytest_cache" ]]; then
    delete_item "$DEEPFLOW_DIR/.pytest_cache"
fi

echo ""

# ========================================
# 第5步：清理过时文档（过程性文件）
# ========================================
echo "【第5步】清理过时过程性文档"
echo "  原因: 这些都是开发过程中的临时记录，已归档"
echo ""

OBSOLETE_FILES=(
    # 过程性进度报告（20+个）
    "PROGRESS.md"
    "PROGRESS_0.0.1.md"
    "PROGRESS_2026-04-16-E2E-COMPLETE.md"
    "PROGRESS_2026-04-16-FINAL.md"
    "PROGRESS_2026-04-16-P0-FIXED.md"
    "PROGRESS_2026-04-16-P02-COMPLETE.md"
    "PROGRESS_2026-04-16-P03-COMPLETE.md"
    "PROGRESS_2026-04-16.md"
    "PROGRESS_2026-04-18-PHASE1.md"
    "PROGRESS_PROMPT_SLIM_V2.md"
    
    # 旧修复记录
    "P0_FIXES_SUMMARY.md"
    "P0_FIX_COMPLETE.md"
    "P0_FIX_PROGRESS.md"
    
    # 旧测试报告
    "FULL_FEATURE_TEST_REPORT.md"
    "T1-T10_MATRIX_TEST_REPORT.md"
    "T6_DETAILED_RETROSPECTIVE.md"
    "TEST_REVIEW_AND_REPAIR_PLAN.md"
    
    # 旧审计/修复记录
    "PIPELINE_ENGINE_FIX_SUMMARY.md"
    "PHASE3_PROTOCOL_AUDIT_REPORT.md"
    "audit_report.json"
    "REPAIR_PLAN_V2_CORRECTED.md"
    "REWRITE_PLAN.md"
    "REPORT_V1.0.md"
    
    # 其他临时文件
    "SYSTEM_HEALTH_CHECK.md"
    "ISSUE_TRACKING.md"
    "ARCHITECTURE_INPUT_OPENCLAW_EVOLUTION_2026.4.10-4.15.md"
    ".session_start_checklist.md"
)

for file in "${OBSOLETE_FILES[@]}"; do
    filepath="$DEEPFLOW_DIR/$file"
    if [[ -f "$filepath" ]]; then
        delete_item "$filepath"
    fi
done

echo ""

# ========================================
# 汇总
# ========================================
echo "=========================================="
if [[ "$DRY_RUN" == true ]]; then
    echo "🔍 预览完成！以上为将要删除的文件"
    echo ""
    echo "确认无误后，执行:"
    echo "  bash cleanup_plan.sh --execute"
else
    echo "✅ 清理完成！"
    echo ""
    echo "如果需要恢复，从备份还原:"
    echo "  cp -r ~/Desktop/DeepFlow_Backup_20260423_134030 ~/.openclaw/workspace/.deepflow"
fi
echo "=========================================="
