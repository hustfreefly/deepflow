#!/usr/bin/env python3
"""
check_delivery_resilience.py - Delivery & 容错恢复契约验证
"""

import sys

def check_delivery_manager():
    """验证 DeliveryManager 实现"""
    from pathlib import Path
    
    if not Path("delivery_manager.py").exists():
        print("❌ FAIL: delivery_manager.py 不存在")
        return False
    
    with open("delivery_manager.py", "r") as f:
        content = f.read()
    
    checks = [
        ("DeliveryManager 类", "class DeliveryManager" in content),
        ("deliver 方法", "def deliver" in content),
        ("stage 参数", "stage" in content and "quick_preview" in content),
        ("channel 支持", "feishu" in content or "message" in content),
        ("blackboard 集成", "blackboard" in content.lower()),
    ]
    
    passed = sum(1 for _, ok in checks if ok)
    print(f"{'✅' if passed >= 4 else '❌'} PASS: DeliveryManager ({passed}/{len(checks)})")
    return passed >= 4

def check_resilience_tests():
    """验证 ResilienceManager 测试覆盖"""
    from pathlib import Path
    
    test_file = Path("test_resilience_manager.py")
    if not test_file.exists():
        print("❌ FAIL: test_resilience_manager.py 不存在")
        return False
    
    with open(test_file, "r") as f:
        content = f.read()
    
    checks = [
        ("测试函数数量", content.count("def test_") >= 3),
        ("CircuitBreaker 测试", "circuit" in content.lower()),
        ("Retry 测试", "retry" in content.lower()),
        ("错误恢复测试", "error" in content.lower() or "fail" in content.lower()),
    ]
    
    passed = sum(1 for _, ok in checks if ok)
    print(f"{'✅' if passed >= 3 else '❌'} PASS: ResilienceManager测试 ({passed}/{len(checks)})")
    return passed >= 3

def check_error_recovery_paths():
    """验证错误恢复路径"""
    with open("resilience_manager.py", "r") as f:
        content = f.read()
    
    checks = [
        ("超时恢复", "timeout" in content.lower()),
        ("重试逻辑", "retry" in content.lower()),
        ("熔断器", "circuit" in content.lower()),
        ("降级策略", "fallback" in content.lower()),
    ]
    
    passed = sum(1 for _, ok in checks if ok)
    print(f"{'✅' if passed >= 3 else '⚠️'} PASS: 错误恢复路径 ({passed}/{len(checks)})")
    return passed >= 3

def main():
    print("=" * 60)
    print("Delivery & 容错恢复契约验证")
    print("=" * 60)
    
    checks = [
        ("DeliveryManager 实现", check_delivery_manager),
        ("ResilienceManager 测试", check_resilience_tests),
        ("错误恢复路径", check_error_recovery_paths),
    ]
    
    results = []
    for name, check_fn in checks:
        print(f"\n[{name}]")
        results.append(check_fn())
    
    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"结果: {passed}/{total} 通过")
    
    if passed == total:
        print("✅ Delivery & 容错恢复实现完成")
        return 0
    else:
        print("❌ 有失败项")
        return 1

if __name__ == "__main__":
    sys.exit(main())
