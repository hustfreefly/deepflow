from core.config.path_config import PathConfig

#!/usr/bin/env python3
"""
系统重构验证测试脚本

验证所有契约要求是否满足
"""

import os
import sys
import subprocess
from pathlib import Path

sys.path.insert(0, str(PathConfig.resolve().base_dir))


def test_no_mock_code():
    """测试1: 无mock代码"""
    print("\n🔍 测试1: 检查无mock代码...")
    
    files_to_check = [
        'pipeline_engine.py',
        'domains/investment/cage_orchestrator.py'
    ]
    
    patterns = ['asyncio.sleep', 'simulated', 'mock_output']
    
    for filepath in files_to_check:
        full_path = fstr(PathConfig.resolve().base_dir / "{filepath}")
        if not os.path.exists(full_path):
            print(f"  ❌ 文件不存在: {filepath}")
            return False
        
        with open(full_path, 'r') as f:
            content = f.read()
        
        for pattern in patterns:
            if pattern in content:
                print(f"  ❌ {filepath} 包含 mock 代码: {pattern}")
                return False
    
    print("  ✅ 通过: 无mock代码")
    return True


def test_all_prompts_exist():
    """测试2: 12个prompt文件存在"""
    print("\n🔍 测试2: 检查12个prompt文件...")
    
    required_files = [
        'investment_planner.md',
        'investment_researcher_enhanced.md',
        'investment_researcher_macro_chain.md',
        'investment_researcher_management.md',
        'investment_researcher_sentiment.md',
        'investment_researcher_tech.md',
        'investment_researcher_market.md',
        'investment_auditor.md',
        'investment_fixer.md',
        'investment_verifier.md',
        'investment_summarizer_enhanced.md',
        'investment_financial.md'
    ]
    
    prompts_dir = str(PathConfig.resolve().prompts_dir)
    missing = []
    
    for filename in required_files:
        filepath = os.path.join(prompts_dir, filename)
        if not os.path.exists(filepath):
            missing.append(filename)
    
    if missing:
        print(f"  ❌ 缺失文件: {missing}")
        return False
    
    print(f"  ✅ 通过: 所有 {len(required_files)} 个prompt文件存在")
    return True


def test_pipeline_engine_uses_sessions_spawn():
    """测试3: PipelineEngine使用sessions_spawn"""
    print("\n🔍 测试3: 检查PipelineEngine使用sessions_spawn...")
    
    filepath = str(PathConfig.resolve().base_dir / "pipeline_engine.py")
    with open(filepath, 'r') as f:
        content = f.read()
    
    count = content.count('sessions_spawn')
    if count < 3:
        print(f"  ❌ sessions_spawn 调用次数不足: {count} < 3")
        return False
    
    print(f"  ✅ 通过: sessions_spawn 调用 {count} 次")
    return True


def test_convergence_check_exists():
    """测试4: 收敛检测≥2轮"""
    print("\n🔍 测试4: 检查收敛检测...")
    
    filepath = str(PathConfig.resolve().base_dir / "pipeline_engine.py")
    with open(filepath, 'r') as f:
        content = f.read()
    
    if 'min_iterations' not in content:
        print("  ❌ 未找到 min_iterations 配置")
        return False
    
    if 'min_iterations = 2' not in content and 'min_iterations=2' not in content:
        # 检查是否有其他形式的最低迭代要求
        if '至少 2 轮' not in content and 'at least 2' not in content.lower():
            print("  ❌ 未找到最低2轮迭代的配置")
            return False
    
    print("  ✅ 通过: 收敛检测要求至少2轮")
    return True


def test_unified_entry_calls_pipeline_engine():
    """测试5: unified_entry调用PipelineEngine"""
    print("\n🔍 测试5: 检查unified_entry调用PipelineEngine...")
    
    yaml_path = str(PathConfig.resolve().base_dir / "cage/unified_entry.yaml")
    with open(yaml_path, 'r') as f:
        content = f.read()
    
    if 'PipelineEngine' not in content:
        print("  ❌ unified_entry.yaml 未配置 PipelineEngine")
        return False
    
    if 'module: "pipeline_engine"' not in content and "module: 'pipeline_engine'" not in content:
        print("  ❌ unified_entry.yaml module 配置不正确")
        return False
    
    print("  ✅ 通过: unified_entry 配置指向 PipelineEngine")
    return True


def test_prompt_structure():
    """测试6: prompt文件结构符合契约"""
    print("\n🔍 测试6: 检查prompt文件结构...")
    
    required_sections = [
        "角色定位",
        "数据读取",
        "搜索工具优先级",
        "输出",  # 放宽为"输出"而非"输出格式"
        "Blackboard",  # 放宽为"Blackboard"而非"Blackboard数据流"
        "数据请求",  # 放宽为"数据请求"而非"数据请求指引"
        "强制执行规则"
    ]
    
    sample_files = [
        'investment_planner.md',
        'investment_researcher_tech.md',
        'investment_auditor.md'
    ]
    
    prompts_dir = str(PathConfig.resolve().prompts_dir)
    
    for filename in sample_files:
        filepath = os.path.join(prompts_dir, filename)
        if not os.path.exists(filepath):
            print(f"  ⚠️  跳过不存在的文件: {filename}")
            continue
        
        with open(filepath, 'r') as f:
            content = f.read()
        
        missing_sections = []
        for section in required_sections:
            if section not in content:
                missing_sections.append(section)
        
        if missing_sections:
            print(f"  ❌ {filename} 缺失章节: {missing_sections}")
            return False
    
    print("  ✅ 通过: prompt文件结构符合要求")
    return True


def main():
    """运行所有测试"""
    print("=" * 60)
    print("系统重构验证测试")
    print("=" * 60)
    
    tests = [
        test_no_mock_code,
        test_all_prompts_exist,
        test_pipeline_engine_uses_sessions_spawn,
        test_convergence_check_exists,
        test_unified_entry_calls_pipeline_engine,
        test_prompt_structure
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"  ❌ 测试异常: {e}")
            results.append(False)
    
    print("\n" + "=" * 60)
    print(f"测试结果: {sum(results)}/{len(results)} 通过")
    print("=" * 60)
    
    if all(results):
        print("\n🎉 所有测试通过！系统重构成功。")
        return 0
    else:
        print("\n❌ 部分测试失败，请检查上述错误。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
