#!/usr/bin/env python3
"""
P0 Fix 验证脚本
验证 Fixer 输入硬编码问题已修复
"""

import sys
import os

DEEPFLOW_BASE = "/Users/allen/.openclaw/workspace/.deepflow"
sys.path.insert(0, DEEPFLOW_BASE)

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

print("\n[P0 Fix 验证]")

# 1. 检查 orchestrator_agent.py 不再硬编码
check(
    "orchestrator_agent.py 无硬编码 issues",
    "\"issues\": \"待填充\"" not in open(f"{DEEPFLOW_BASE}/domains/solution/orchestrator_agent.py").read(),
    "发现硬编码 issues"
)

# 2. 检查 build_fixer_task_with_audit 函数存在
from domains.solution import task_builder
check(
    "build_fixer_task_with_audit 函数存在",
    hasattr(task_builder, 'build_fixer_task_with_audit'),
    "函数不存在"
)

# 3. 检查函数可用
try:
    task = task_builder.build_fixer_task_with_audit(
        "test_session", "测试主题", "/path/to/audit.json"
    )
    check(
        "build_fixer_task_with_audit 可调用",
        isinstance(task, str) and "/path/to/audit.json" in task,
        "函数返回异常"
    )
except Exception as e:
    check("build_fixer_task_with_audit 可调用", False, str(e))

# 4. 检查完整契约验证仍然通过
import subprocess
result = subprocess.run(
    ["python3", f"{DEEPFLOW_BASE}/cage/validate_refactor.py"],
    capture_output=True,
    text=True
)
check(
    "validate_refactor.py 仍然通过",
    result.returncode == 0,
    f"验证失败: {result.stderr[:100]}"
)

print(f"\n结果: {passed}/{passed+failed} 通过")
sys.exit(0 if failed == 0 else 1)
