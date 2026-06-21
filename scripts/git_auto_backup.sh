#!/bin/bash
# Git 自动备份脚本
# 每天自动 add + commit + push 到 GitHub

set -euo pipefail

# 配置
DEEPFLOW_DIR="/Users/allen/.openclaw/workspace/.deepflow"
LOG_FILE="$DEEPFLOW_DIR/logs/git_backup_$(date +%Y%m%d).log"
MAX_LOG_DAYS=7

# 确保日志目录存在
mkdir -p "$(dirname "$LOG_FILE")"

# 日志函数
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# 清理旧日志
cleanup_old_logs() {
    local log_dir="$DEEPFLOW_DIR/logs"
    if [ -d "$log_dir" ]; then
        find "$log_dir" -name "git_backup_*.log" -mtime +$MAX_LOG_DAYS -delete 2>/dev/null || true
        log "已清理 $MAX_LOG_DAYS 天前的日志"
    fi
}

# 主备份逻辑
backup() {
    log "========== Git 自动备份开始 =========="
    
    # 切换到 DeepFlow 目录
    cd "$DEEPFLOW_DIR" || {
        log "❌ 无法进入目录: $DEEPFLOW_DIR"
        exit 1
    }
    
    # 检查 git 状态
    if [ -z "$(git status --porcelain)" ]; then
        log "✅ 没有需要提交的更改"
        log "========== Git 自动备份完成 =========="
        exit 0
    fi
    
    # 统计变更
    local changed_files=$(git status --porcelain | wc -l | tr -d ' ')
    log "📊 检测到 $changed_files 个文件变更"
    
    # Git add
    git add .
    log "✅ Git add 完成"
    
    # Git commit
    local commit_msg="auto-backup: $(date '+%Y-%m-%d %H:%M:%S') - $changed_files files changed"
    git commit -m "$commit_msg"
    log "✅ Git commit: $commit_msg"
    
    # Git push
    git push origin main 2>&1 | tee -a "$LOG_FILE"
    log "✅ Git push 完成"
    
    log "========== Git 自动备份完成 =========="
}

# 错误处理
trap 'log "❌ 备份失败: $BASH_COMMAND"' ERR

# 执行
cleanup_old_logs
backup
