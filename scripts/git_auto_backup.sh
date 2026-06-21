#!/bin/bash
# Git 本地备份脚本
# 每天自动 add + commit（本地），不自动 push 到 GitHub
# 手动 push 命令: cd .deepflow && git push origin main
# 安全等级: Production

set -euo pipefail

# ==================== 配置 ====================
DEEPFLOW_DIR="/Users/allen/.openclaw/workspace/.deepflow"
LOG_FILE="$DEEPFLOW_DIR/logs/git_backup_$(date +%Y%m%d).log"
PID_FILE="/tmp/git_auto_backup.pid"
MAX_LOG_DAYS=7
BRANCH="main"

# ==================== 安全检查 ====================

# 检查目录是否存在
if [ ! -d "$DEEPFLOW_DIR" ]; then
    echo "❌ 目录不存在: $DEEPFLOW_DIR" >&2
    exit 1
fi

# 检查 .gitignore 是否存在
if [ ! -f "$DEEPFLOW_DIR/.gitignore" ]; then
    echo "❌ .gitignore 不存在，备份已中止（防止敏感文件泄露）" >&2
    exit 1
fi

# 检查敏感目录是否被 gitignore
check_gitignore() {
    # 核心敏感目录（必须精确匹配或被路径覆盖）
    local critical_dirs=(".credentials" "blackboard")
    # 通用敏感模式（模糊匹配即可）
    local pattern_checks=("__pycache__" ".env" "*.pyc" "node_modules")
    
    local missing=()
    
    # 精确检查核心目录
    for dir in "${critical_dirs[@]}"; do
        if ! grep -q "$dir" "$DEEPFLOW_DIR/.gitignore" 2>/dev/null; then
            missing+=("$dir")
        fi
    done
    
    # 模糊检查通用模式（匹配任意位置包含该关键词的条目）
    for pattern in "${pattern_checks[@]}"; do
        if ! grep -q "$pattern" "$DEEPFLOW_DIR/.gitignore" 2>/dev/null; then
            missing+=("$pattern")
        fi
    done
    
    if [ ${#missing[@]} -gt 0 ]; then
        echo "❌ .gitignore 缺少以下敏感条目: ${missing[*]}" >&2
        echo "请添加这些条目到 .gitignore 后再运行备份" >&2
        exit 1
    fi
}

check_gitignore

# ==================== 并发控制 ====================

# PID 文件锁（防止并发执行）
acquire_lock() {
    if [ -f "$PID_FILE" ]; then
        local existing_pid=$(cat "$PID_FILE")
        if kill -0 "$existing_pid" 2>/dev/null; then
            echo "❌ 备份已在运行 (PID: $existing_pid)" >&2
            exit 1
        else
            echo "⚠️ 清理过期的 PID 文件 (PID: $existing_pid)" >&2
            rm -f "$PID_FILE"
        fi
    fi
    echo $$ > "$PID_FILE"
}

release_lock() {
    rm -f "$PID_FILE"
}

trap release_lock EXIT
acquire_lock

# ==================== 日志 ====================

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

# ==================== 主备份逻辑 ====================

backup() {
    log "========== Git 自动备份开始 =========="
    
    # 切换到 DeepFlow 目录
    cd "$DEEPFLOW_DIR" || {
        log "❌ 无法进入目录: $DEEPFLOW_DIR"
        exit 1
    }
    
    # 检查当前分支
    local current_branch=$(git rev-parse --abbrev-ref HEAD)
    if [ "$current_branch" != "$BRANCH" ]; then
        log "⚠️ 当前分支是 $current_branch，不是 $BRANCH"
        log "尝试切换到 $BRANCH..."
        git checkout "$BRANCH" || {
            log "❌ 无法切换到 $BRANCH 分支"
            exit 1
        }
    fi
    
    # 检查 git 状态
    if [ -z "$(git status --porcelain)" ]; then
        log "✅ 没有需要提交的更改"
        log "========== Git 自动备份完成 =========="
        exit 0
    fi
    
    # 统计变更
    local changed_files=$(git status --porcelain | wc -l | tr -d ' ')
    log "📊 检测到 $changed_files 个文件变更"
    
    # 显示变更文件列表（用于审核）
    log "变更文件列表:"
    git status --porcelain | while read -r line; do
        log "  $line"
    done
    
    # Git add
    git add .
    log "✅ Git add 完成"
    
    # Git commit
    local commit_msg="auto-backup: $(date '+%Y-%m-%d %H:%M:%S') - $changed_files files changed"
    git commit -m "$commit_msg"
    log "✅ Git commit: $commit_msg"
    
    # 提示手动 push
    log "💡 本地提交完成，如需推送到 GitHub，请执行:"
    log "   cd $DEEPFLOW_DIR && git push origin $BRANCH"
    
    log "========== Git 本地备份完成 =========="
}

# 错误处理
trap 'log "❌ 备份失败: $BASH_COMMAND (exit code: $?)"; release_lock; exit 1' ERR

# 执行
cleanup_old_logs
backup
exit 0
