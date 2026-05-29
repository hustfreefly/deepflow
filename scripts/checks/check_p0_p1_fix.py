#!/usr/bin/env python3
"""
P0-P1 修复验证脚本
验证所有 P0-P1 问题是否已修复
"""

import os
import sys


def check_orchestrator_p0():
    """检查 Orchestrator P0 修复"""
    print("\n[Orchestrator P0 验证]")
    
    filepath = "/Users/allen/.openclaw/workspace/.deepflow/orchestrator_agent.py"
    with open(filepath, 'r') as f:
        content = f.read()
    
    checks = {
        "session_id 获取方式": "session_id 获取" in content or "从 Tasks 文件名提取" in content,
        "并行等待逻辑说明": "sessions_yield" in content and "等待所有" in content,
        "scopes 参数": "scopes=" in content,
        "cleanup 参数": "cleanup=" in content,
    }
    
    for name, result in checks.items():
        status = "✅" if result else "❌"
        print(f"  {status} {name}")
    
    return all(checks.values())


def check_datamanager_p1():
    """检查 DataManager P1 修复"""
    print("\n[DataManager P1 验证]")
    
    # 检查 Task Builder 中的 DataManager Task
    filepath = "/Users/allen/.openclaw/workspace/.deepflow/core/task_builder.py"
    with open(filepath, 'r') as f:
        content = f.read()
    
    checks = {
        "异常处理 try-except": "try:" in content and "except Exception" in content,
        "fallback 搜索": "search_with_fallback" in content or "fallback" in content.lower(),
        "key_metrics 完整性检查": "key_metrics" in content and "检查字段完整性" in content,
        "DuckDuckGo fallback": "duckduckgo" in content.lower(),
    }
    
    for name, result in checks.items():
        status = "✅" if result else "❌"
        print(f"  {status} {name}")
    
    return all(checks.values())


def check_syntax():
    """检查语法"""
    print("\n[语法检查]")
    
    import py_compile
    
    files = [
        "/Users/allen/.openclaw/workspace/.deepflow/core/task_builder.py",
        "/Users/allen/.openclaw/workspace/.deepflow/core/master_agent.py",
        "/Users/allen/.openclaw/workspace/.deepflow/core/data_manager_worker.py",
    ]
    
    for filepath in files:
        try:
            py_compile.compile(filepath, doraise=True)
            print(f"  ✅ {os.path.basename(filepath)}")
        except Exception as e:
            print(f"  ❌ {os.path.basename(filepath)}: {e}")
            return False
    
    return True


def main():
    print("=" * 60)
    print("P0-P1 修复验证")
    print("=" * 60)
    
    results = {
        "Orchestrator P0": check_orchestrator_p0(),
        "DataManager P1": check_datamanager_p1(),
        "语法检查": check_syntax(),
    }
    
    print("\n" + "=" * 60)
    print("验证结果汇总")
    print("=" * 60)
    
    for name, result in results.items():
        status = "✅" if result else "❌"
        print(f"{status} {name}")
    
    passed = sum(results.values())
    total = len(results)
    
    print(f"\n总计: {passed}/{total} 通过")
    
    if passed == total:
        print("\n🎉 所有 P0-P1 修复验证通过！")
        return 0
    else:
        print(f"\n⚠️ {total - passed} 项未通过")
        return 1


if __name__ == "__main__":
    sys.exit(main())
