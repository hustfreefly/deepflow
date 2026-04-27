#!/usr/bin/env python3
"""
测试脚本路径替换契约验证脚本
"""

import os
import sys

DEEPFLOW_BASE = "/Users/allen/.openclaw/workspace/.deepflow"

passed = 0
failed = 0

def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} - {detail}")

print("\n" + "="*70)
print("测试脚本路径替换契约验证")
print("="*70)

# 检查各目录
dirs = ["tests/unit", "tests/integration", "tests/contract", "tests/cage"]

for d in dirs:
    dir_path = os.path.join(DEEPFLOW_BASE, d)
    if not os.path.exists(dir_path):
        check(f"{d} 目录存在", True, "目录不存在，跳过")
        continue
    
    # 查找硬编码路径
    count = 0
    for root, _, files in os.walk(dir_path):
        for f in files:
            if f.endswith('.py'):
                file_path = os.path.join(root, f)
                with open(file_path, 'r') as fh:
                    content = fh.read()
                    if '/Users/allen/' in content:
                        count += 1
    
    check(f"{d} 无硬编码路径", count == 0, f"发现 {count} 个文件包含硬编码路径")

print("\n" + "="*70)
print(f"验证结果: {passed}/{passed+failed} 通过")
print("="*70)

sys.exit(0 if failed == 0 else 1)
