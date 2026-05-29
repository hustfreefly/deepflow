#!/bin/bash
# DeepFlow 回归测试运行脚本

set -e

echo "================================"
echo "DeepFlow 回归测试套件"
echo "================================"
echo ""

# 检查 pytest
if ! command -v pytest &> /dev/null; then
    echo "❌ pytest 未安装，正在安装..."
    pip3 install pytest pytest-asyncio
fi

echo "📋 测试选项:"
echo "  1) 运行所有测试"
echo "  2) 运行冒烟测试（快速）"
echo "  3) 运行单元测试"
echo "  4) 运行 T1-T2 基础测试"
echo "  5) 运行特定测试"
echo ""

# 默认运行冒烟测试
TEST_OPTION="${1:-2}"

case $TEST_OPTION in
    1)
        echo "🚀 运行所有测试..."
        pytest test_regression.py -v
        ;;
    2)
        echo "🔥 运行冒烟测试..."
        pytest test_regression.py::TestRegressionSuite::test_t1_simple_task -v
        pytest test_regression.py::test_smoke_import -v
        pytest test_regression.py::test_smoke_coordinator_init -v
        echo ""
        echo "✅ 冒烟测试通过！核心功能正常。"
        ;;
    3)
        echo "🧪 运行单元测试..."
        pytest test_regression.py::TestPipelineEngineCore -v
        pytest test_regression.py::TestConfigDrivenBehavior -v
        ;;
    4)
        echo "🎯 运行 T1-T2 基础测试..."
        pytest test_regression.py::TestRegressionSuite::test_t1_simple_task -v
        pytest test_regression.py::TestRegressionSuite::test_t2_standard_task -v
        ;;
    5)
        echo "🎯 运行特定测试: $2"
        pytest "$2" -v
        ;;
    *)
        echo "❌ 无效选项: $TEST_OPTION"
        echo "用法: ./run_tests.sh [1|2|3|4|5] [test_name]"
        exit 1
        ;;
esac

echo ""
echo "================================"
echo "测试完成"
echo "================================"
