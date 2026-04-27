#!/usr/bin/env python3
"""
Orchestrator Base 路径替换契约验证脚本
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
print("Orchestrator Base 契约验证")
print("="*70)

# 检查文件是否存在
import os
ob_file = f"{DEEPFLOW_BASE}/core/orchestrator_base.py"
check("文件存在", os.path.exists(ob_file))

if os.path.exists(ob_file):
    with open(ob_file, 'r') as f:
        content = f.read()
    
    # 检查硬编码路径
    has_hardcode = '/Users/allen/' in content
    check("无硬编码路径", not has_hardcode, "发现 /Users/allen/" if has_hardcode else "")
    
    # 检查 PathConfig 导入
    has_import = 'from core.config.path_config import PathConfig' in content
    check("PathConfig导入", has_import)
    
    # 检查 sys.path 使用 PathConfig
    has_syspath = 'PathConfig' in content and 'sys.path' in content
    check("sys.path使用PathConfig", has_syspath)
    
    # 检查 PromptLoader 使用 PathConfig
    has_prompt = 'PathConfig' in content and 'prompts' in content
    check("PromptLoader使用PathConfig", has_prompt)
    
    # 检查 DomainConfig 加载使用 PathConfig
    has_domain = 'PathConfig.resolve' in content or 'config_path' in content and 'PathConfig' in content
    check("DomainConfig使用PathConfig", has_domain)

# 检查导入
try:
    result = subprocess.run(
        ["python3", "-c", "from core.orchestrator_base import BaseOrchestrator; print('OK')"],
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
