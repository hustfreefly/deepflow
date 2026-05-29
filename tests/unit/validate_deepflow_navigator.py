#!/usr/bin/env python3
"""
DeepFlow 导航页验证脚本
验证 /deepflow 技能的 SKILL.md 是否符合契约要求
"""

import sys
from pathlib import Path

def validate_navigator():
    """验证 DeepFlow 导航页是否符合契约"""
    
    skill_path = Path.home() / ".openclaw/workspace/skills/deepflow/SKILL.md"
    
    if not skill_path.exists():
        print(f"❌ FAIL: SKILL.md 不存在: {skill_path}")
        return False
    
    content = skill_path.read_text(encoding='utf-8')
    
    # 验证必需文本
    required_texts = [
        "🚀 DeepFlow — 专业级多Agent协作系统",
        "从想法到方案，一站式搞定",
        "你现在处于哪个阶段？",
        "Spec Pro",
        "Solution Pro",
        "Investment",
        "Research Pro",
        "5-10分钟",
        "40-60分钟",
        "30-40分钟",
        "直接回复你的想法，我来安排 👇"
    ]
    
    all_passed = True
    
    for text in required_texts:
        if text in content:
            print(f"✅ PASS: 必需文本存在: {text}")
        else:
            print(f"❌ FAIL: 缺少必需文本: {text}")
            all_passed = False
    
    # 验证模块完整性
    modules = ["Spec Pro", "Solution Pro", "Investment", "Research Pro"]
    for module in modules:
        if module in content:
            print(f"✅ PASS: 模块存在: {module}")
        else:
            print(f"❌ FAIL: 缺少模块: {module}")
            all_passed = False
    
    # 验证耗时说明
    time_descriptions = ["5-10分钟", "40-60分钟", "30-40分钟"]
    for time_desc in time_descriptions:
        if time_desc in content:
            print(f"✅ PASS: 耗时说明存在: {time_desc}")
        else:
            print(f"❌ FAIL: 缺少耗时说明: {time_desc}")
            all_passed = False
    
    # 验证 CTA
    if "直接回复你的想法，我来安排 👇" in content:
        print(f"✅ PASS: CTA 存在")
    else:
        print(f"❌ FAIL: 缺少 CTA")
        all_passed = False
    
    # 统计字数
    navigator_section = extract_navigator_content(content)
    if navigator_section:
        char_count = len(navigator_section)
        if char_count <= 160:
            print(f"✅ PASS: 字数符合要求 ({char_count}/160)")
        else:
            print(f"⚠️  WARNING: 字数超标 ({char_count}/160)")
    else:
        print(f"⚠️  WARNING: 无法提取导航内容")
    
    return all_passed

def extract_navigator_content(content):
    """提取导航页的实际内容"""
    lines = content.split('\n')
    start_idx = None
    end_idx = None
    
    for i, line in enumerate(lines):
        if '🚀 DeepFlow' in line:
            start_idx = i
        if start_idx and '直接回复你的想法' in line:
            end_idx = i + 1
            break
    
    if start_idx is not None and end_idx is not None:
        return '\n'.join(lines[start_idx:end_idx])
    return None

if __name__ == "__main__":
    print("=" * 60)
    print("DeepFlow 导航页验证")
    print("=" * 60)
    
    if validate_navigator():
        print("\n✅ 验证通过！导航页符合契约要求")
        sys.exit(0)
    else:
        print("\n❌ 验证失败！请检查导航页内容")
        sys.exit(1)
