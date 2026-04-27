#!/usr/bin/env python3
"""
第六批：批量替换 core/ 和 domains/ 中剩余硬编码路径
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
    if "sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow'" in content:
        if 'from core.config.path_config import PathConfig' not in content:
            import_line = "from core.config.path_config import PathConfig\n\n"
            content = import_line + content
        
        content = re.sub(
            r"sys\.path\.insert\(0, '/Users/allen/\.openclaw/workspace/\.deepflow/?'\)",
            "sys.path.insert(0, str(PathConfig.resolve().base_dir))",
            content
        )
    
    # 2. 替换 DEEPFLOW_BASE 硬编码
    content = re.sub(
        r'DEEPFLOW_BASE = "/Users/allen/\.openclaw/workspace/\.deepflow"',
        'DEEPFLOW_BASE = str(PathConfig.resolve().base_dir)',
        content
    )
    
    # 3. 替换 Path 硬编码路径（cage_dir, base_dir 等）
    content = re.sub(
        r'Path\(cage_dir or "/Users/allen/\.openclaw/workspace/\.deepflow/cage"\)',
        'Path(cage_dir or PathConfig.resolve().base_dir / "cage")',
        content
    )
    
    content = re.sub(
        r'Path\(base_dir or "/Users/allen/\.openclaw/workspace/\.deepflow/blackboard"\)',
        'Path(base_dir or PathConfig.resolve().blackboard_dir)',
        content
    )
    
    content = re.sub(
        r'Path\(base_dir or "/Users/allen/\.openclaw/workspace/\.deepflow/checkpoints"\)',
        'Path(base_dir or PathConfig.resolve().base_dir / "checkpoints")',
        content
    )
    
    # 4. 替换其他硬编码路径
    content = re.sub(
        r'"/Users/allen/\.openclaw/workspace/\.deepflow/([^"]+)"',
        lambda m: f'str(PathConfig.resolve().base_dir / "{m.group(1)}")',
        content
    )
    
    content = re.sub(
        r"'/Users/allen/\.openclaw/workspace/\.deepflow/([^']+)'",
        lambda m: f'str(PathConfig.resolve().base_dir / "{m.group(1)}")',
        content
    )
    
    # 5. 替换 f-string 中的硬编码路径
    content = re.sub(
        r'f"/Users/allen/\.openclaw/workspace/\.deepflow/([^"]+)"',
        lambda m: f'f"{{str(PathConfig.resolve().base_dir)}}/{m.group(1)}"',
        content
    )
    
    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  ✅ 已更新: {os.path.relpath(filepath, DEEPFLOW_BASE)}")
        return True
    return False

# 处理 core/ 下所有文件
updated_count = 0
core_dir = f"{DEEPFLOW_BASE}/core"
for root, _, files in os.walk(core_dir):
    for filename in files:
        if filename.endswith('.py'):
            filepath = os.path.join(root, filename)
            if process_file(filepath):
                updated_count += 1

# 处理 domains/ 下所有文件
domains_dir = f"{DEEPFLOW_BASE}/domains"
for root, _, files in os.walk(domains_dir):
    for filename in files:
        if filename.endswith('.py'):
            filepath = os.path.join(root, filename)
            if process_file(filepath):
                updated_count += 1

print(f"\n✅ 共更新 {updated_count} 个文件")
