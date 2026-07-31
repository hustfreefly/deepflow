#!/bin/bash
# Deliver Pro Pulse 通用调度器 — 扫描所有活跃项目
# 替代硬编码的 launchd plist，支持多项目
# 
# 用法: ./pulse_all.sh
# 由 launchd 每 5 分钟触发

set -e

DEEPFLOW_ROOT="/Users/allen/.openclaw/workspace/.deepflow"
BLACKBOARD_ROOT="$DEEPFLOW_ROOT/blackboard"
export PYTHONPATH="/Users/allen/.openclaw/workspace"
export OPENCLAW_SESSION_ID="cron-pulse"

cd "$DEEPFLOW_ROOT"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Pulse 通用调度器启动"

# 扫描所有项目
for project_dir in "$BLACKBOARD_ROOT"/*/; do
    [ ! -d "$project_dir" ] && continue
    project_name=$(basename "$project_dir")
    
    # 跳过非项目目录
    [[ "$project_name" == "_"* ]] && continue
    [[ "$project_name" == "."* ]] && continue
    
    # 检查是否有 ship_package（有调度需求）
    has_ship=false
    for candidate in "$project_dir/ship_pro/ship_package.md" "$project_dir/ship_pro/ship_track.json" "$project_dir/ship_pro/ship_package.json" "$project_dir/ship_pro/stages/ship_package.json"; do
        [ -f "$candidate" ] && has_ship=true && break
    done
    
    # 检查是否已完成（有 .deliver_completed.json 则跳过）
    has_completed=false
    [ -f "$project_dir/.deliver_completed.json" ] && has_completed=true
    
    # 只处理有 ship_package 但未完成的项目
    if [ "$has_ship" = true ] && [ "$has_completed" = false ]; then
        echo "  → 检查项目: $project_name"
        
        # 执行 pulse
        /opt/homebrew/bin/python3 -m domains.deliver_pro.pulse_cli pulse --project "$project_name" 2>&1 | while read line; do
            echo "    $line"
        done
        
        # 检查退出码
        exit_code=${PIPESTATUS[0]}
        if [ $exit_code -eq 10 ]; then
            echo "    ⚠️  被护栏拦截（主 agent 同步调用）"
        elif [ $exit_code -eq 2 ]; then
            echo "    ⚠️  被锁（另一个 pulse 运行中）"
        elif [ $exit_code -eq 3 ]; then
            echo "    ✅ 已完成"
        elif [ $exit_code -ne 0 ]; then
            echo "    ❌ 错误 (exit=$exit_code)"
        fi
    fi
done

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Pulse 通用调度器结束"
