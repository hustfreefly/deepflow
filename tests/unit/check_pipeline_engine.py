#!/usr/bin/env python3
"""
check_pipeline_engine.py - PipelineEngine 契约验证

验证点：
1. _normalize_threshold 幂等性
2. 无重复缩放（* 100）
3. 阈值判断正确性
4. 编码规范 P0=0
"""

import sys
from pathlib import Path

# 添加路径
sys.path.insert(0, str(Path(__file__).parent))

from pipeline_engine import PipelineEngine
from config_loader import ConfigLoader


def test_normalize_threshold_idempotent():
    """测试_normalize_threshold幂等性"""
    print("\n[TEST] _normalize_threshold 幂等性")
    
    # Mock PipelineEngine创建
    loader = ConfigLoader()
    config = loader.load_domain_config("general")
    engine = PipelineEngine(config)
    
    # 测试用例
    test_cases = [
        (0.85, 85.0),    # 0-1尺度输入
        (85.0, 85.0),   # 0-100尺度输入（已转换）
        (0.0, 0.0),     # 边界
        (1.0, 100.0),   # 边界
    ]
    
    all_pass = True
    for input_val, expected in test_cases:
        result = engine._normalize_threshold(input_val)
        status = "✅" if result == expected else "❌"
        print(f"  {status} _normalize_threshold({input_val}) = {result} (期望 {expected})")
        if result != expected:
            all_pass = False
    
    return all_pass


def test_no_double_scaling():
    """验证没有重复缩放"""
    print("\n[TEST] 无重复缩放（* 100检查）")
    
    # 读取源码检查
    source = Path("pipeline_engine.py").read_text()
    
    # 检查危险模式：_normalize_threshold(...) * 100
    dangerous_patterns = [
        "_normalize_threshold(.*) * 100",
        "_normalize_threshold(.*) *100",
    ]
    
    found_violations = []
    lines = source.split('\n')
    for i, line in enumerate(lines, 1):
        if "_normalize_threshold" in line and ("* 100" in line or "*100" in line):
            found_violations.append((i, line.strip()))
    
    if found_violations:
        print("  ❌ 发现重复缩放违规：")
        for line_no, content in found_violations:
            print(f"     行{line_no}: {content}")
        return False
    else:
        print("  ✅ 无重复缩放违规")
        return True


def test_threshold_comparison():
    """测试阈值比较逻辑"""
    print("\n[TEST] 阈值比较逻辑")
    
    loader = ConfigLoader()
    config = loader.load_domain_config("general")
    engine = PipelineEngine(config)
    
    # 模拟：target_score=0.85应该转换为85.0
    target_0_1 = 0.85
    target_normalized = engine._normalize_threshold(target_0_1)
    
    # 模拟评分85.0应该等于target
    test_score = 85.0
    
    print(f"  输入target_score: {target_0_1} (0-1尺度)")
    print(f"  转换后: {target_normalized} (0-100尺度)")
    print(f"  测试评分: {test_score}")
    print(f"  比较: {test_score} >= {target_normalized} → {test_score >= target_normalized}")
    
    if target_normalized == 85.0 and test_score >= target_normalized:
        print("  ✅ 阈值比较逻辑正确")
        return True
    else:
        print("  ❌ 阈值比较逻辑错误")
        return False


def test_coding_standards():
    """编码规范验证"""
    print("\n[TEST] 编码规范 P0=0")
    
    from coding_standards import CodingStandardsChecker
    
    checker = CodingStandardsChecker(strict_mode=False)
    report = checker.check_file(Path("pipeline_engine.py"))
    
    print(f"  P0={report.p0_count}, P1={report.p1_count}, P2={report.p2_count}")
    
    if report.p0_count == 0:
        print("  ✅ 编码规范合规")
        return True
    else:
        print("  ❌ 存在P0违规：")
        for v in report.violations:
            if v.level == "P0":
                print(f"     行{v.line}: {v.rule}")
        return False


def main():
    """主入口"""
    print("=" * 60)
    print("PipelineEngine 契约验证")
    print("=" * 60)
    
    tests = [
        ("normalize_threshold幂等性", test_normalize_threshold_idempotent),
        ("无重复缩放", test_no_double_scaling),
        ("阈值比较逻辑", test_threshold_comparison),
        ("编码规范", test_coding_standards),
    ]
    
    results = []
    for name, test_fn in tests:
        try:
            passed = test_fn()
            results.append((name, passed))
        except Exception as e:
            print(f"  ❌ 测试执行失败: {e}")
            results.append((name, False))
    
    print("\n" + "=" * 60)
    print("验证结果汇总")
    print("=" * 60)
    
    all_passed = True
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {status}: {name}")
        if not passed:
            all_passed = False
    
    print("=" * 60)
    if all_passed:
        print("🎉 所有契约验证通过！可以提交。")
        return 0
    else:
        print("⚠️  存在失败项，请修复后再提交。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
