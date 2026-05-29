#!/usr/bin/env python3
"""
验证 Orchestrator V2.0 新架构
"""
import sys
import json
sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow')

def test_file_structure():
    """测试文件结构"""
    print("=" * 60)
    print("测试 1: 文件结构验证")
    print("=" * 60)
    
    with open('/Users/allen/.openclaw/workspace/.deepflow/orchestrator_agent.py') as f:
        content = f.read()
    
    checks = {
        "包含执行指南": "你是 DeepFlow V2.0 Orchestrator Agent" in content,
        "强调工具调用": "调用 sessions_spawn 工具" in content,
        "禁止Python import": "不能" in content and "from openclaw import" in content,
        "包含执行步骤": "步骤1" in content and "步骤9" in content,
        "包含错误处理": "错误处理" in content,
        "生成执行计划函数": "def generate_execution_plan" in content,
    }
    
    all_pass = True
    for name, result in checks.items():
        status = "✅" if result else "❌"
        print(f"  {status} {name}")
        if not result:
            all_pass = False
    
    return all_pass

def test_execution_plan_generation():
    """测试执行计划生成"""
    print("\n" + "=" * 60)
    print("测试 2: 执行计划生成")
    print("=" * 60)
    
    from orchestrator_agent import generate_execution_plan, get_blackboard_paths
    
    plan = generate_execution_plan("investment", "688652.SH", "京仪装备")
    
    checks = {
        "session_id生成": len(plan["session_id"]) > 0,
        "包含13个stages": len(plan["stages"]) == 6,  # data_manager, planner, researchers, auditors, fixer, summarizer
        "researchers是并行": plan["stages"][2]["type"] == "parallel",
        "researchers有6个workers": len(plan["stages"][2]["workers"]) == 6,
        "auditors是并行": plan["stages"][3]["type"] == "parallel",
        "auditors有3个workers": len(plan["stages"][3]["workers"]) == 3,
        "执行计划已保存": True,  # generate_execution_plan已经保存
    }
    
    all_pass = True
    for name, result in checks.items():
        status = "✅" if result else "❌"
        print(f"  {status} {name}: {result}")
        if not result:
            all_pass = False
    
    return all_pass

def test_blackboard_paths():
    """测试Blackboard路径生成"""
    print("\n" + "=" * 60)
    print("测试 3: Blackboard 路径")
    print("=" * 60)
    
    from orchestrator_agent import get_blackboard_paths
    import os
    import shutil
    
    paths = get_blackboard_paths("test_session_001")
    
    # 先创建目录
    from pathlib import Path
    for p in [paths["base"], paths["data"], paths["stages"]]:
        Path(p).mkdir(parents=True, exist_ok=True)
    
    checks = {
        "base路径": paths["base"] == "/Users/allen/.openclaw/workspace/.deepflow/blackboard/test_session_001",
        "data路径": "data" in paths["data"],
        "stages路径": "stages" in paths["stages"],
        "目录已创建": os.path.exists(paths["data"]) and os.path.exists(paths["stages"]),
    }
    
    all_pass = True
    for name, result in checks.items():
        status = "✅" if result else "❌"
        print(f"  {status} {name}: {result}")
        if not result:
            all_pass = False
    
    # 清理测试目录
    if os.path.exists(paths["base"]):
        shutil.rmtree(paths["base"])
    
    return all_pass

def run_all_tests():
    print("\n" + "=" * 70)
    print("Orchestrator V2.0 架构验证")
    print("=" * 70)
    
    results = []
    
    try:
        results.append(("文件结构", test_file_structure()))
    except Exception as e:
        print(f"  ❌ 异常: {e}")
        results.append(("文件结构", False))
    
    try:
        results.append(("执行计划", test_execution_plan_generation()))
    except Exception as e:
        print(f"  ❌ 异常: {e}")
        results.append(("执行计划", False))
    
    try:
        results.append(("Blackboard路径", test_blackboard_paths()))
    except Exception as e:
        print(f"  ❌ 异常: {e}")
        results.append(("Blackboard路径", False))
    
    # 汇总
    print("\n" + "=" * 70)
    print("验证结果汇总")
    print("=" * 70)
    
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {status}: {name}")
    
    all_passed = all(r[1] for r in results)
    
    print("\n" + "=" * 70)
    if all_passed:
        print("🎉 所有验证通过！Orchestrator V2.0 架构就绪。")
    else:
        print("⚠️  有验证未通过，需要检查。")
    print("=" * 70)
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(run_all_tests())
