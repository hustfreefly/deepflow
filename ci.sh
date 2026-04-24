#!/bin/bash
#
# DeepFlow CI 脚本
#
# 运行完整的验证流程：
# 1. 契约验证 (cage/validate.py --all)
# 2. 编码规范检查 (cage/check_standards.py --all)
# 3. 契约测试 (pytest tests/contract/)
# 4. 单元测试 (pytest tests/unit/)
#
# 用法：
#   ./ci.sh              # 运行完整 CI
#   ./ci.sh --quick      # 快速模式（跳过慢测试）
#   ./ci.sh --contract   # 仅运行契约验证
#   ./ci.sh --unit       # 仅运行单元测试
#   ./ci.sh --help       # 显示帮助
#

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

# 计数器
TOTAL_PASSED=0
TOTAL_FAILED=0
FAILED_STEPS=()

# =============================================================================
# 辅助函数
# =============================================================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[PASS]${NC} $1"
}

log_error() {
    echo -e "${RED}[FAIL]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_header() {
    echo ""
    echo "================================================================================"
    echo "  $1"
    echo "================================================================================"
}

print_separator() {
    echo "--------------------------------------------------------------------------------"
}

run_step() {
    local step_name="$1"
    local command="$2"
    
    print_header "$step_name"
    
    if eval "$command"; then
        log_success "$step_name 完成"
        ((TOTAL_PASSED++))
        return 0
    else
        log_error "$step_name 失败"
        ((TOTAL_FAILED++))
        FAILED_STEPS+=("$step_name")
        return 1
    fi
}

# =============================================================================
# 验证步骤
# =============================================================================

validate_contracts() {
    log_info "验证契约笼子..."
    cd "$PROJECT_ROOT"
    python cage/validate.py --all
}

check_standards() {
    log_info "检查编码规范..."
    cd "$PROJECT_ROOT"
    python cage/check_standards.py --all
}

run_contract_tests() {
    log_info "运行契约测试..."
    cd "$PROJECT_ROOT"
    python -m pytest tests/contract/ -v --tb=short
}

run_unit_tests() {
    log_info "运行单元测试..."
    cd "$PROJECT_ROOT"
    
    if [ "$QUICK_MODE" = true ]; then
        log_warn "快速模式：跳过慢测试"
        python -m pytest tests/unit/ -v --tb=short -m "not slow"
    else
        python -m pytest tests/unit/ -v --tb=short
    fi
}

run_integration_tests() {
    log_info "运行集成测试..."
    cd "$PROJECT_ROOT"
    
    if [ "$QUICK_MODE" = true ]; then
        log_warn "快速模式：跳过集成测试"
        return 0
    fi
    
    python -m pytest tests/integration/ -v --tb=short
}

# =============================================================================
# 模式函数
# =============================================================================

run_full_ci() {
    print_header "DeepFlow CI - 完整验证流程"
    
    # 1. 契约验证
    run_step "契约验证" "validate_contracts" || true
    
    # 2. 编码规范检查
    run_step "编码规范检查" "check_standards" || true
    
    # 3. 契约测试
    run_step "契约测试" "run_contract_tests" || true
    
    # 4. 单元测试
    run_step "单元测试" "run_unit_tests" || true
    
    # 5. 集成测试（非快速模式）
    if [ "$QUICK_MODE" = false ]; then
        run_step "集成测试" "run_integration_tests" || true
    fi
    
    print_summary
}

run_contract_only() {
    print_header "DeepFlow CI - 仅契约验证"
    
    run_step "契约验证" "validate_contracts"
    run_step "契约测试" "run_contract_tests"
    
    print_summary
}

run_unit_only() {
    print_header "DeepFlow CI - 仅单元测试"
    
    run_step "单元测试" "run_unit_tests"
    
    print_summary
}

# =============================================================================
# 汇总报告
# =============================================================================

print_summary() {
    echo ""
    echo "================================================================================"
    echo "                              CI 汇总报告"
    echo "================================================================================"
    
    if [ ${#FAILED_STEPS[@]} -eq 0 ]; then
        log_success "所有检查通过 ✓"
        echo ""
        echo "总计: $TOTAL_PASSED 通过, $TOTAL_FAILED 失败"
        echo ""
        return 0
    else
        log_error "存在失败的检查"
        echo ""
        echo "失败的步骤:"
        for step in "${FAILED_STEPS[@]}"; do
            echo "  - $step"
        done
        echo ""
        echo "总计: $TOTAL_PASSED 通过, $TOTAL_FAILED 失败"
        echo ""
        return 1
    fi
}

# =============================================================================
# 帮助信息
# =============================================================================

show_help() {
    cat << EOF
DeepFlow CI 脚本

用法:
    ./ci.sh [选项]

选项:
    --quick, -q      快速模式（跳过慢测试和集成测试）
    --contract, -c   仅运行契约验证和契约测试
    --unit, -u       仅运行单元测试
    --integration, -i 仅运行集成测试
    --help, -h       显示此帮助信息

示例:
    ./ci.sh              # 运行完整 CI
    ./ci.sh --quick      # 快速模式
    ./ci.sh --contract   # 仅契约验证
    ./ci.sh --unit       # 仅单元测试

环境变量:
    PYTHONPATH      Python 模块搜索路径
    CI              设置为任意值以启用 CI 模式（减少输出）

EOF
}

# =============================================================================
# 主入口
# =============================================================================

main() {
    # 解析参数
    QUICK_MODE=false
    RUN_MODE="full"
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --quick|-q)
                QUICK_MODE=true
                shift
                ;;
            --contract|-c)
                RUN_MODE="contract"
                shift
                ;;
            --unit|-u)
                RUN_MODE="unit"
                shift
                ;;
            --integration|-i)
                RUN_MODE="integration"
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                log_error "未知选项: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    # 切换到项目根目录
    cd "$PROJECT_ROOT"
    
    # 设置 Python 路径
    export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"
    
    log_info "项目根目录: $PROJECT_ROOT"
    log_info "Python 路径: $PYTHONPATH"
    
    # 检查必需工具
    if ! command -v python &> /dev/null; then
        log_error "未找到 Python"
        exit 1
    fi
    
    if ! command -v pytest &> /dev/null && ! python -c "import pytest" 2>/dev/null; then
        log_warn "未找到 pytest，尝试安装..."
        pip install pytest pytest-asyncio
    fi
    
    # 根据模式运行
    case $RUN_MODE in
        full)
            run_full_ci
            ;;
        contract)
            run_contract_only
            ;;
        unit)
            run_unit_only
            ;;
        integration)
            run_integration_tests
            print_summary
            ;;
    esac
}

# 运行主函数
main "$@"
