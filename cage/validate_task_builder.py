#!/usr/bin/env python3
"""
Task Builder 路径替换契约验证脚本
"""

import sys
import subprocess

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
print("Task Builder 契约验证")
print("="*70)

# 检查文件是否存在
import os
tb_file = f"{DEEPFLOW_BASE}/domains/solution/task_builder.py"
check("文件存在", os.path.exists(tb_file))

if os.path.exists(tb_file):
    with open(tb_file, 'r') as f:
        content = f.read()
    
    # 检查硬编码路径
    has_hardcode = '/Users/allen/' in content
    check("无硬编码路径", not has_hardcode, "发现 /Users/allen/" if has_hardcode else "")
    
    # 检查 PathConfig 导入
    has_import = 'from core.config.path_config import PathConfig' in content
    check("PathConfig导入", has_import)
    
    # 检查 PathConfig 使用
    has_usage = 'PathConfig.resolve' in content or 'config.get_blackboard_path' in content
    check("PathConfig使用", has_usage)
    
    # 检查是否还有旧式 blackboard/ 路径（未使用变量）
    has_relative = False
    lines = content.split('\n')
    for line in lines:
        if 'blackboard/' in line and '_DEEPFLOW_BASE' not in line and 'get_blackboard_path' not in line:
            # 忽略注释行
            stripped = line.strip()
            if not stripped.startswith('#'):
                has_relative = True
                break
    check("无硬编码blackboard路径", not has_relative, "发现未替换的 blackboard/ 路径")

# 检查导入
try:
    result = subprocess.run(
        ["python3", "-c", "from domains.solution.task_builder import build_data_collection_task; print('OK')"],
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
