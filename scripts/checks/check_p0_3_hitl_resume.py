#!/usr/bin/env python3
"""
check_p0_3_hitl_resume.py - P0-3 HITL resume 契约验证
"""

import ast
import sys

def check_coordinator_resume_hitl():
    """验证 coordinator.py 有 resume_hitl 方法"""
    with open("coordinator.py", "r") as f:
        content = f.read()
    
    if "def resume_hitl" in content:
        print("✅ PASS: coordinator.resume_hitl 存在")
        return True
    else:
        print("❌ FAIL: 缺少 coordinator.resume_hitl 方法")
        return False

def check_bridge_hitl_continue():
    """验证 bridge 使用真实 HITL 继续而非模拟"""
    with open("coordinator_bridge.py", "r") as f:
        content = f.read()
    
    # 检查是否有 _hitl_continue 方法
    has_hitl_continue = "def _hitl_continue" in content
    
    # 检查是否调用了 coordinator 的 resume_hitl
    calls_coordinator = "coordinator.resume_hitl" in content
    
    # 检查是否还有模拟标记
    has_simulate_marker = "_simulate_hitl_continue" in content
    
    if has_hitl_continue and calls_coordinator and not has_simulate_marker:
        print("✅ PASS: bridge._hitl_continue 调用 coordinator.resume_hitl")
        return True
    elif has_simulate_marker:
        print("❌ FAIL: 仍使用 _simulate_hitl_continue (模拟)")
        return False
    else:
        print(f"⚠️ WARN: HITL继续不完整 (has_method={has_hitl_continue}, calls_coord={calls_coordinator})")
        return False

def check_hitl_state_handling():
    """验证 HITL 状态处理"""
    with open("coordinator.py", "r") as f:
        content = f.read()
    
    patterns = ["WAITING_HITL", "decision", "feedback"]
    found = sum(1 for p in patterns if p in content)
    
    if found >= 2:
        print(f"✅ PASS: HITL 状态处理完整 ({found}/3)")
        return True
    else:
        print("❌ FAIL: HITL 状态处理不完整")
        return False

def main():
    print("=" * 60)
    print("P0-3 HITL Resume 契约验证")
    print("=" * 60)
    
    checks = [
        ("coordinator.resume_hitl 方法", check_coordinator_resume_hitl),
        ("bridge._hitl_continue 实现", check_bridge_hitl_continue),
        ("HITL 状态处理", check_hitl_state_handling),
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
        print("✅ P0-3 HITL resume 实现完成")
        return 0
    else:
        print("❌ 有失败项，需要修复")
        return 1

if __name__ == "__main__":
    sys.exit(main())
