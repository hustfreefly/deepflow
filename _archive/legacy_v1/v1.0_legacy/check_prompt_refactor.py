#!/usr/bin/env python3
"""
Prompt分层重构验证脚本
验证契约文件、分层Prompt、加载器是否完整
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow/')

from cage.prompt_loader import CagePromptLoader


def validate_contract():
    """验证契约文件"""
    print("=" * 60)
    print("验证契约文件 (prompt_layers.yaml)")
    print("=" * 60)
    
    contract_path = Path("/Users/allen/.openclaw/workspace/.deepflow/cage/prompt_layers.yaml")
    
    if not contract_path.exists():
        print("❌ 契约文件不存在")
        return False
    
    print(f"✅ 契约文件存在: {contract_path}")
    
    # 加载契约
    loader = CagePromptLoader('investment')
    contract = loader.contract
    
    # 检查必需字段
    required_keys = ['cage_version', 'domain', 'layers', 'workers', 'convergence']
    for key in required_keys:
        if key not in contract:
            print(f"❌ 契约缺少必需字段: {key}")
            return False
        print(f"✅ 契约包含字段: {key}")
    
    # 检查layers结构
    layers = contract['layers']
    if 'core' not in layers:
        print("❌ layers缺少core定义")
        return False
    print("✅ layers包含core定义")
    
    if 'steps' not in layers:
        print("❌ layers缺少steps定义")
        return False
    print("✅ layers包含steps定义")
    
    # 检查steps数量
    steps = layers['steps']
    expected_steps = ['data_collection', 'search', 'worker_dispatch']
    actual_steps = [step['name'] for step in steps]
    
    for expected in expected_steps:
        if expected not in actual_steps:
            print(f"❌ steps缺少: {expected}")
            return False
        print(f"✅ steps包含: {expected}")
    
    print("\n✅ 契约文件验证通过\n")
    return True


def validate_prompts():
    """验证分层Prompt文件"""
    print("=" * 60)
    print("验证分层Prompt文件")
    print("=" * 60)
    
    loader = CagePromptLoader('investment')
    
    # 验证Core Prompt
    try:
        core = loader.load_core()
        core_size = len(core)
        
        # Core应该在3K以内
        if core_size > 3000:
            print(f"❌ Core Prompt过大: {core_size} chars (应 < 3000)")
            return False
        
        print(f"✅ Core Prompt: {core_size} chars (< 3K)")
        
        # 检查核心内容
        required_content = ['身份', '强制契约', '收敛检测', '输出Schema']
        for content in required_content:
            if content not in core:
                print(f"❌ Core Prompt缺少: {content}")
                return False
            print(f"✅ Core Prompt包含: {content}")
        
    except Exception as e:
        print(f"❌ Core Prompt加载失败: {e}")
        return False
    
    # 验证Step Prompts
    steps = ['data_collection', 'search', 'worker_dispatch']
    for step_name in steps:
        try:
            step_content = loader.load_step(step_name)
            step_size = len(step_content)
            
            # Step应该在2-3K以内
            max_size = 3000 if step_name == 'worker_dispatch' else 2000
            if step_size > max_size:
                print(f"❌ Step '{step_name}' Prompt过大: {step_size} chars (应 < {max_size})")
                return False
            
            print(f"✅ Step '{step_name}': {step_size} chars (< {max_size})")
            
        except Exception as e:
            print(f"❌ Step '{step_name}' Prompt加载失败: {e}")
            return False
    
    print("\n✅ 分层Prompt文件验证通过\n")
    return True


def validate_loader():
    """验证Prompt加载器"""
    print("=" * 60)
    print("验证Prompt加载器 (CagePromptLoader)")
    print("=" * 60)
    
    loader = CagePromptLoader('investment')
    
    # 测试load_core
    try:
        core = loader.load_core()
        print(f"✅ load_core() 成功: {len(core)} chars")
    except Exception as e:
        print(f"❌ load_core() 失败: {e}")
        return False
    
    # 测试load_step
    steps = ['data_collection', 'search', 'worker_dispatch']
    for step_name in steps:
        try:
            step = loader.load_step(step_name)
            print(f"✅ load_step('{step_name}') 成功: {len(step)} chars")
        except Exception as e:
            print(f"❌ load_step('{step_name}') 失败: {e}")
            return False
    
    # 测试get_next_step
    next_step = loader.get_next_step('data_collection')
    if next_step != 'search':
        print(f"❌ get_next_step('data_collection') 返回错误: {next_step}")
        return False
    print(f"✅ get_next_step('data_collection') = '{next_step}'")
    
    next_step = loader.get_next_step('search')
    if next_step != 'worker_dispatch':
        print(f"❌ get_next_step('search') 返回错误: {next_step}")
        return False
    print(f"✅ get_next_step('search') = '{next_step}'")
    
    next_step = loader.get_next_step('worker_dispatch')
    if next_step is not None:
        print(f"❌ get_next_step('worker_dispatch') 应返回None，实际: {next_step}")
        return False
    print(f"✅ get_next_step('worker_dispatch') = None (最后一个)")
    
    # 测试get_completion_signal
    signal = loader.get_completion_signal('data_collection')
    if '[PHASE_COMPLETE: data_collection]' not in signal:
        print(f"❌ get_completion_signal('data_collection') 返回错误: {signal}")
        return False
    print(f"✅ get_completion_signal('data_collection') = '{signal}'")
    
    # 测试get_worker_config
    try:
        researcher_config = loader.get_worker_config('researcher')
        print(f"✅ get_worker_config('researcher') 成功: {researcher_config}")
    except Exception as e:
        print(f"❌ get_worker_config('researcher') 失败: {e}")
        return False
    
    # 测试get_convergence_rules
    try:
        convergence = loader.get_convergence_rules()
        print(f"✅ get_convergence_rules() 成功: {convergence}")
    except Exception as e:
        print(f"❌ get_convergence_rules() 失败: {e}")
        return False
    
    print("\n✅ Prompt加载器验证通过\n")
    return True


def validate_orchestrator_entry():
    """验证Orchestrator Agent入口脚本"""
    print("=" * 60)
    print("验证Orchestrator Agent入口脚本")
    print("=" * 60)
    
    entry_path = Path("/Users/allen/.openclaw/workspace/.deepflow/orchestrator_cage_agent.py")
    
    if not entry_path.exists():
        print(f"❌ Orchestrator入口脚本不存在: {entry_path}")
        return False
    
    print(f"✅ Orchestrator入口脚本存在: {entry_path}")
    
    # 检查文件大小
    file_size = entry_path.stat().st_size
    print(f"✅ 文件大小: {file_size} bytes")
    
    # 检查关键内容
    with open(entry_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    required_imports = ['CagePromptLoader', 'os', 'sys']
    for imp in required_imports:
        if imp not in content:
            print(f"❌ 入口脚本缺少导入: {imp}")
            return False
        print(f"✅ 入口脚本包含导入: {imp}")
    
    required_functions = ['main', 'load_core', 'load_step']
    for func in required_functions:
        if func not in content:
            print(f"❌ 入口脚本缺少函数调用: {func}")
            return False
        print(f"✅ 入口脚本包含函数调用: {func}")
    
    print("\n✅ Orchestrator Agent入口脚本验证通过\n")
    return True


def main():
    """主验证流程"""
    print("\n" + "=" * 60)
    print("DeepFlow V2.0 Prompt分层重构验证")
    print("=" * 60 + "\n")
    
    results = []
    
    # 1. 验证契约文件
    results.append(("契约文件", validate_contract()))
    
    # 2. 验证分层Prompt
    results.append(("分层Prompt", validate_prompts()))
    
    # 3. 验证加载器
    results.append(("Prompt加载器", validate_loader()))
    
    # 4. 验证入口脚本
    results.append(("入口脚本", validate_orchestrator_entry()))
    
    # 汇总结果
    print("=" * 60)
    print("验证结果汇总")
    print("=" * 60)
    
    all_passed = True
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{name}: {status}")
        if not passed:
            all_passed = False
    
    print("=" * 60)
    
    if all_passed:
        print("\n🎉 所有验证通过！Prompt分层重构完成。")
        print("\n重构成果:")
        print("- 契约文件: cage/prompt_layers.yaml")
        print("- Core Prompt: prompts/investment/orchestrator/core.md (~1.2K)")
        print("- Step Prompts: prompts/investment/orchestrator/step*.md (~0.3-0.9K)")
        print("- Prompt加载器: cage/prompt_loader.py")
        print("- Orchestrator入口: orchestrator_cage_agent.py")
        print("\n原18K单体Prompt已重构为分层架构，保持Agent执行方式。")
        return 0
    else:
        print("\n❌ 部分验证失败，请检查上述错误。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
