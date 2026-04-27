#!/usr/bin/env python3
"""
批量替换测试脚本中的硬编码路径
"""

import os
import re

DEEPFLOW_BASE = "/Users/allen/.openclaw/workspace/.deepflow"

def process_file(filepath):
    """处理单个文件"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original = content
    
    # 1. 替换 sys.path.insert 硬编码路径
    if "sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow" in content:
        # 检查是否已有 PathConfig 导入
        if 'from core.config.path_config import PathConfig' not in content:
            # 在文件开头添加导入
            import_line = "from core.config.path_config import PathConfig\n\n"
            content = import_line + content
        
        # 替换 sys.path.insert
        content = re.sub(
            r"sys\.path\.insert\(0, '/Users/allen/\.openclaw/workspace/\.deepflow/?'\)",
            "sys.path.insert(0, str(PathConfig.resolve().base_dir))",
            content
        )
    
    # 2. 替换硬编码的 DEEPFLOW_HOME
    content = re.sub(
        r"DEEPFLOW_HOME = '/Users/allen/\.openclaw/workspace/\.deepflow'",
        "DEEPFLOW_HOME = str(PathConfig.resolve().base_dir)",
        content
    )
    
    # 3. 替换硬编码的 contract_path
    content = re.sub(
        r'"/Users/allen/\.openclaw/workspace/\.deepflow/cage/([^"]+)"',
        r'str(PathConfig.resolve().base_dir / "cage" / "\1")',
        content
    )
    
    # 4. 替换硬编码的 prompts_dir
    content = re.sub(
        r"'/Users/allen/\.openclaw/workspace/\.deepflow/prompts/'",
        "str(PathConfig.resolve().prompts_dir)",
        content
    )
    
    # 5. 替换其他硬编码路径
    content = re.sub(
        r"'/Users/allen/\.openclaw/workspace/\.deepflow/([^']+)'",
        r'str(PathConfig.resolve().base_dir / "\1")',
        content
    )
    
    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  ✅ 已更新: {os.path.relpath(filepath, DEEPFLOW_BASE)}")
        return True
    return False

# 处理所有测试文件
updated_count = 0
test_dirs = [
    f"{DEEPFLOW_BASE}/tests/unit",
    f"{DEEPFLOW_BASE}/tests/integration",
    f"{DEEPFLOW_BASE}/tests/contract",
    f"{DEEPFLOW_BASE}/tests/cage",
    f"{DEEPFLOW_BASE}/tests"
]

for dir_path in test_dirs:
    if not os.path.exists(dir_path):
        continue
    for root, _, files in os.walk(dir_path):
        for filename in files:
            if filename.endswith('.py'):
                filepath = os.path.join(root, filename)
                if process_file(filepath):
                    updated_count += 1

print(f"\n✅ 共更新 {updated_count} 个文件")
