#!/usr/bin/env python3
"""
P0 修复验证脚本
验证所有 P0 文件是否符合契约
"""

import os
import sys

sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow')


def check_file_exists(filepath, description):
    """检查文件是否存在"""
    print(f"\n[Check] {description}")
    if os.path.exists(filepath):
        print(f"  ✅ 存在: {filepath}")
        return True
    else:
        print(f"  ❌ 不存在: {filepath}")
        return False


def check_orchestrator_guide():
    """检查 Orchestrator 是否为文本指南"""
    print("\n[Check] Orchestrator Agent 指南格式")
    
    filepath = "/Users/allen/.openclaw/workspace/.deepflow/orchestrator_agent.py"
    with open(filepath, 'r') as f:
        content = f.read()
    
    # 检查不应包含 Python 类
    forbidden = ["class OrchestratorV4", "def __init__", "import sys"]
    for item in forbidden:
        if item in content:
            print(f"  ❌ 包含 Python 代码: {item}")
            return False
    
    # 检查必须包含的内容
    required = [
        "Orchestrator Agent",
        "sessions_spawn",
        "sessions_yield",
        "DataManager Worker",
        "Summarizer Worker"
    ]
    for item in required:
        if item not in content:
            print(f"  ❌ 缺少内容: {item}")
            return False
    
    print("  ✅ 格式正确（文本指南）")
    return True


def check_master_agent():
    """检查 Master Agent"""
    print("\n[Check] Master Agent 功能")
    
    try:
        from core.master_agent import init_session, generate_tasks, save_tasks
        
        # 测试初始化
        session_id = init_session("688981.SH", "中芯国际", "半导体制造")
        assert "中芯国际" in session_id
        print(f"  ✅ 初始化成功: {session_id}")
        
        # 测试 Task 生成
        tasks = generate_tasks(session_id, "688981.SH", "中芯国际", "半导体制造")
        assert "data_manager" in tasks
        assert "planner" in tasks
        assert "researchers" in tasks
        assert len(tasks["researchers"]) == 6
        print(f"  ✅ Task 生成成功: {len(tasks)} 个主要 Task")
        
        # 测试保存
        tasks_path = save_tasks(tasks, session_id)
        assert os.path.exists(tasks_path)
        print(f"  ✅ 保存成功: {tasks_path}")
        
        return True
        
    except Exception as e:
        print(f"  ❌ 功能测试失败: {e}")
        return False


def check_data_manager():
    """检查 DataManager Worker"""
    print("\n[Check] DataManager Worker 功能")
    
    filepath = "/Users/allen/.openclaw/workspace/.deepflow/core/data_manager_worker.py"
    with open(filepath, 'r') as f:
        content = f.read()
    
    # 检查必须包含的内容
    required = [
        "bootstrap_phase",
        "run_bootstrap",
        "run_supplement_search",
        "gemini_search",
        "duckduckgo_search"
    ]
    for item in required:
        if item not in content:
            print(f"  ❌ 缺少功能: {item}")
            return False
    
    print("  ✅ 功能完整")
    return True


def main():
    """运行所有检查"""
    print("=" * 60)
    print("P0 修复验证")
    print("=" * 60)
    
    checks = [
        ("Orchestrator 指南文件", 
         check_file_exists("/Users/allen/.openclaw/workspace/.deepflow/orchestrator_agent.py", 
                          "Orchestrator Agent 指南")),
        ("Orchestrator 格式", check_orchestrator_guide()),
        ("Master Agent 文件", 
         check_file_exists("/Users/allen/.openclaw/workspace/.deepflow/core/master_agent.py", 
                          "Master Agent")),
        ("Master Agent 功能", check_master_agent()),
        ("DataManager Worker 文件", 
         check_file_exists("/Users/allen/.openclaw/workspace/.deepflow/core/data_manager_worker.py", 
                          "DataManager Worker")),
        ("DataManager Worker 功能", check_data_manager()),
    ]
    
    print("\n" + "=" * 60)
    print("验证结果汇总")
    print("=" * 60)
    
    passed = 0
    for name, result in checks:
        status = "✅" if result else "❌"
        print(f"{status} {name}")
        if result:
            passed += 1
    
    total = len(checks)
    print(f"\n总计: {passed}/{total} 通过")
    
    if passed == total:
        print("\n🎉 所有 P0 修复验证通过！")
        return 0
    else:
        print(f"\n⚠️ {total - passed} 项未通过")
        return 1


if __name__ == "__main__":
    sys.exit(main())
