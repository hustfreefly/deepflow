#!/usr/bin/env python3
"""
DeepClaw → Research Pro 批量替换脚本
契约编号: EXEC-RENAME-RESEARCH-PRO-V2.0
"""

import re
from pathlib import Path
from typing import List, Dict

WORKSPACE = Path("/Users/allen/.openclaw/workspace")
DEEPFLOW = WORKSPACE / ".deepflow"

# 改名映射表
RENAME_MAP = {
    "DeepClaw": "ResearchPro",
    "deepclaw": "research_pro",
    "deep_claw": "research_pro",
    "DEEPCLAW": "RESEARCH_PRO",
    "Deep Claw": "Research Pro",
    "deep claw": "research pro",
}

# 必须修改的文件（Category A）
FILES_TO_MODIFY = [
    # 核心代码
    ".deepflow/skills/research-pro/lib/orchestrator.py",
    ".deepflow/skills/research-pro/lib/citation_verifier.py",
    ".deepflow/skills/research-pro/lib/tier_classifier.py",
    ".deepflow/skills/research-pro/lib/keyword_generator.py",
    ".deepflow/skills/research-pro/lib/source_registry.py",
    
    # 测试文件
    ".deepflow/tests/research_pro/test_orchestrator.py",
    ".deepflow/tests/research_pro/test_citation_verifier.py",
    ".deepflow/tests/research_pro/test_source_registry.py",
    ".deepflow/tests/research_pro/test_keyword_generator.py",
    ".deepflow/tests/research_pro/test_tier_classifier.py",
    ".deepflow/tests/e2e/run_real_e2e.py",
    
    # 文档
    ".deepflow/skills/research-pro/SKILL.md",
    "skills/deepflow/SKILL.md",
    ".deepflow/cage/deepclaw_dev_instructions.md",
    ".deepflow/tests/unit/validate_deepflow_navigator.py",
    ".deepflow/cage/deepclaw_v1.0.yaml",
]

def replace_in_file(file_path: Path, rename_map: Dict[str, str]) -> int:
    """在文件中执行替换，返回替换次数"""
    if not file_path.exists():
        print(f"   ⚠️ 文件不存在: {file_path}")
        return 0
    
    try:
        content = file_path.read_text(encoding='utf-8')
        original_content = content
        
        # 按长度降序替换，避免部分匹配
        sorted_pairs = sorted(rename_map.items(), key=lambda x: -len(x[0]))
        
        for old, new in sorted_pairs:
            # 使用正则表达式进行精确匹配
            pattern = re.compile(re.escape(old))
            content = pattern.sub(new, content)
        
        if content != original_content:
            file_path.write_text(content, encoding='utf-8')
            return 1
        return 0
    except Exception as e:
        print(f"   ❌ 处理失败 {file_path}: {e}")
        return -1

def main():
    print("=" * 80)
    print("DeepClaw → Research Pro 批量替换")
    print("=" * 80)
    
    total_replaced = 0
    files_modified = 0
    files_failed = 0
    
    for rel_path in FILES_TO_MODIFY:
        file_path = WORKSPACE / rel_path
        print(f"\n处理: {rel_path}")
        
        result = replace_in_file(file_path, RENAME_MAP)
        
        if result > 0:
            print(f"   ✅ 已修改")
            files_modified += 1
            total_replaced += result
        elif result == 0:
            print(f"   ⚪ 无需修改")
        else:
            files_failed += 1
    
    print("\n" + "=" * 80)
    print("替换统计:")
    print("=" * 80)
    print(f"   修改文件: {files_modified}")
    print(f"   跳过文件: {len(FILES_TO_MODIFY) - files_modified - files_failed}")
    print(f"   失败文件: {files_failed}")
    
    # 验证
    print("\n" + "=" * 80)
    print("验证检查:")
    print("=" * 80)
    
    import subprocess
    
    # 检查是否还有 DeepClaw 引用（排除备份和归档）
    result = subprocess.run(
        ["grep", "-r", "DeepClaw\\|deepclaw", 
         "--include=*.py", "--include=*.md", "--include=*.yaml",
         "--exclude-dir=*.backup", "--exclude-dir=blackboard", "--exclude-dir=.dreams",
         str(WORKSPACE)],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        remaining = result.stdout.strip().split('\n')
        print(f"   ⚠️ 仍有 {len(remaining)} 处 DeepClaw 引用:")
        for line in remaining[:10]:  # 只显示前10个
            print(f"      {line}")
        if len(remaining) > 10:
            print(f"      ... 还有 {len(remaining) - 10} 处")
    else:
        print(f"   ✅ 未发现残留的 DeepClaw 引用")
    
    print("\n" + "=" * 80)
    print("替换完成！")
    print("=" * 80)

if __name__ == "__main__":
    main()
