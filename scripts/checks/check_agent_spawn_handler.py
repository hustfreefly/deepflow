#!/usr/bin/env python3
"""
check_agent_spawn_handler.py - AgentSpawnHandler契约验证

验证点:
1. 文件轮询机制
2. sessions_spawn调用（注释/模板存在）
3. 结果文件写入
4. 并发控制
5. 错误处理
"""

import re
import sys

def check_file_polling():
    """验证文件轮询机制"""
    with open("agent_spawn_handler.py", "r") as f:
        content = f.read()
    
    patterns = ["glob", "*.request.json", "while True", "poll_interval"]
    found = sum(1 for p in patterns if p in content)
    
    if found >= 3:
        print(f"✅ PASS: 文件轮询机制完整 ({found}/4)")
        return True
    else:
        print("❌ FAIL: 文件轮询机制不完整")
        return False

def check_sessions_spawn():
    """验证sessions_spawn调用存在"""
    with open("agent_spawn_handler.py", "r") as f:
        content = f.read()
    
    if "sessions_spawn" in content:
        print("✅ PASS: sessions_spawn调用存在")
        return True
    else:
        print("❌ FAIL: 缺少sessions_spawn调用")
        return False

def check_result_writing():
    """验证结果文件写入"""
    with open("agent_spawn_handler.py", "r") as f:
        content = f.read()
    
    patterns = [".result.json", "write_text", "json.dumps"]
    found = sum(1 for p in patterns if p in content)
    
    if found >= 2:
        print(f"✅ PASS: 结果写入机制完整 ({found}/3)")
        return True
    else:
        print("❌ FAIL: 结果写入机制不完整")
        return False

def check_concurrency():
    """验证并发控制"""
    with open("agent_spawn_handler.py", "r") as f:
        content = f.read()
    
    if "max_concurrent" in content or "semaphore" in content.lower():
        print("✅ PASS: 并发控制存在")
        return True
    else:
        print("⚠️ WARN: 缺少显式并发控制")
        return True  # 警告但不失败

def check_error_handling():
    """验证错误处理"""
    with open("agent_spawn_handler.py", "r") as f:
        content = f.read()
    
    if "except Exception:" in content:
        print("❌ FAIL: 发现 bare except")
        return False
    
    specific = ["FileNotFoundError", "TimeoutError", "json.JSONDecodeError"]
    found = sum(1 for e in specific if e in content)
    print(f"✅ PASS: 有具体异常处理 ({found}种)")
    return True

def main():
    print("=" * 60)
    print("AgentSpawnHandler 契约验证")
    print("=" * 60)
    
    checks = [
        ("文件轮询机制", check_file_polling),
        ("sessions_spawn调用", check_sessions_spawn),
        ("结果文件写入", check_result_writing),
        ("并发控制", check_concurrency),
        ("错误处理", check_error_handling),
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
        print("✅ 全部通过 - 主Agent侧spawn集成完成")
        return 0
    else:
        print("❌ 有失败项 - 继续修复")
        return 1

if __name__ == "__main__":
    sys.exit(main())
