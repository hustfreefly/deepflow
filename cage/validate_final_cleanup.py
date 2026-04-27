#!/usr/bin/env python3
"""
最终清理契约验证脚本
"""

import os
import subprocess

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
print("最终清理契约验证")
print("="*70)

# 检查临时脚本
import glob
temp_scripts = glob.glob(f"{DEEPFLOW_BASE}/cage/refactor_*.py")
check("无临时脚本", len(temp_scripts) == 0, f"发现 {len(temp_scripts)} 个: {temp_scripts}")

# 检查 core/ 硬编码
try:
    result = subprocess.run(
        ["grep", "-r", "/Users/allen/", f"{DEEPFLOW_BASE}/core/", "--include=*.py"],
        capture_output=True, text=True
    )
    count = len([l for l in result.stdout.split('\n') if l.strip()])
    check("core/ 无硬编码", count == 0, f"发现 {count} 处")
except Exception as e:
    check("core/ 无硬编码", False, str(e))

# 检查 domains/ 硬编码
try:
    result = subprocess.run(
        ["grep", "-r", "/Users/allen/", f"{DEEPFLOW_BASE}/domains/", "--include=*.py"],
        capture_output=True, text=True
    )
    count = len([l for l in result.stdout.split('\n') if l.strip()])
    check("domains/ 无硬编码", count == 0, f"发现 {count} 处")
except Exception as e:
    check("domains/ 无硬编码", False, str(e))

# 检查 tests/ 硬编码
try:
    result = subprocess.run(
        ["grep", "-r", "/Users/allen/", f"{DEEPFLOW_BASE}/tests/", "--include=*.py"],
        capture_output=True, text=True
    )
    lines = [l for l in result.stdout.split('\n') if l.strip() and '__pycache__' not in l]
    check("tests/ 无硬编码", len(lines) == 0, f"发现 {len(lines)} 处")
except Exception as e:
    check("tests/ 无硬编码", False, str(e))

# 检查 PathConfig 使用
check("orchestrator_base 使用 PathConfig", 
      os.path.exists(f"{DEEPFLOW_BASE}/core/orchestrator_base.py") and 
      'from core.config.path_config import PathConfig' in open(f"{DEEPFLOW_BASE}/core/orchestrator_base.py").read())

check("task_builder 使用 PathConfig",
      os.path.exists(f"{DEEPFLOW_BASE}/domains/solution/task_builder.py") and
      'from core.config.path_config import PathConfig' in open(f"{DEEPFLOW_BASE}/domains/solution/task_builder.py").read())

# 检查契约笼子文件完整性
required_cages = [
    "cage/path_config_contract.yaml",
    "cage/task_builder_contract.yaml", 
    "cage/orchestrator_base_contract.yaml",
    "cage/investment_domain_contract.yaml",
    "cage/test_scripts_contract.yaml",
    "cage/final_cleanup_contract.yaml"
]

all_exist = all(os.path.exists(f"{DEEPFLOW_BASE}/{f}") for f in required_cages)
check("契约笼子文件完整", all_exist)

print("\n" + "="*70)
print(f"验证结果: {passed}/{passed+failed} 通过")
print("="*70)

import sys
sys.exit(0 if failed == 0 else 1)
