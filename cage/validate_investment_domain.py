#!/usr/bin/env python3
"""
Investment 领域路径替换契约验证脚本
"""

import sys
import subprocess
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

print("\n" + "="*70)
print("Investment 领域契约验证")
print("="*70)

# 检查所有文件是否存在
files = [
    f"{DEEPFLOW_BASE}/domains/investment/__init__.py",
    f"{DEEPFLOW_BASE}/domains/investment/orchestrator.py",
    f"{DEEPFLOW_BASE}/domains/investment/cage_orchestrator.py"
]

for f in files:
    check(f"文件存在: {os.path.basename(f)}", os.path.exists(f))

# 检查所有文件中的硬编码路径
all_content = ""
for f in files:
    if os.path.exists(f):
        with open(f, 'r') as fh:
            content = fh.read()
            all_content += content
            
            # 检查单个文件
            has_hardcode = '/Users/allen/' in content
            check(f"{os.path.basename(f)} 无硬编码", not has_hardcode, 
                  f"发现 /Users/allen/" if has_hardcode else "")
            
            # 检查 PathConfig 导入
            has_import = 'from core.config.path_config import PathConfig' in content
            check(f"{os.path.basename(f)} PathConfig导入", has_import)

# 检查 sys.path 使用 PathConfig
for f in files:
    if os.path.exists(f):
        with open(f, 'r') as fh:
            content = fh.read()
            has_syspath = 'PathConfig' in content and 'sys.path' in content
            check(f"{os.path.basename(f)} sys.path使用PathConfig", has_syspath)

# 检查导入
try:
    result = subprocess.run(
        ["python3", "-c", "from domains.investment.orchestrator import InvestmentOrchestrator; print('OK')"],
        cwd=DEEPFLOW_BASE,
        capture_output=True,
        text=True
    )
    check("可导入", result.returncode == 0, result.stderr[:200] if result.returncode != 0 else "")
except Exception as e:
    check("可导入", False, str(e))

print("\n" + "="*70)
print(f"验证结果: {passed}/{passed+failed} 通过")
print("="*70)

sys.exit(0 if failed == 0 else 1)
