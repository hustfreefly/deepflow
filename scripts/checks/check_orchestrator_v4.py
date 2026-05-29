#!/usr/bin/env python3
"""
Orchestrator V4.0 契约验证脚本
"""

import os
import json
import sys

sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow')


def check_python_syntax():
    """检查 Python 语法"""
    print("\n[Check 1] Python 语法检查")
    try:
        import py_compile
        py_compile.compile('/Users/allen/.openclaw/workspace/.deepflow/orchestrator_agent.py', doraise=True)
        print("  ✅ 语法正确")
        return True
    except Exception as e:
        print(f"  ❌ 语法错误: {e}")
        return False


def check_imports():
    """检查模块导入"""
    print("\n[Check 2] 模块导入检查")
    try:
        from orchestrator_agent import run_initialization, generate_all_tasks
        print("  ✅ 主函数导入成功")
        return True
    except Exception as e:
        print(f"  ❌ 导入失败: {e}")
        return False


def check_task_generation():
    """检查 Task 生成"""
    print("\n[Check 3] Task 生成检查")
    try:
        from orchestrator_agent import generate_all_tasks
        tasks = generate_all_tasks(
            session_id="test_session",
            company_code="688652.SH",
            company_name="京仪装备"
        )
        
        required_keys = ["data_manager", "planner", "researchers", "auditors", "fixer", "summarizer"]
        for key in required_keys:
            if key not in tasks:
                print(f"  ❌ 缺少 Task: {key}")
                return False
        
        # 检查 Researchers
        if len(tasks["researchers"]) != 6:
            print(f"  ❌ Researchers 数量不对: {len(tasks['researchers'])}")
            return False
        
        # 检查 Auditors
        if len(tasks["auditors"]) != 3:
            print(f"  ❌ Auditors 数量不对: {len(tasks['auditors'])}")
            return False
        
        print(f"  ✅ 所有 Task 生成成功")
        print(f"     DataManager: {len(tasks['data_manager'])} 字符")
        print(f"     Planner: {len(tasks['planner'])} 字符")
        print(f"     Researchers: {len(tasks['researchers'])} 个")
        print(f"     Auditors: {len(tasks['auditors'])} 个")
        print(f"     Summarizer: {len(tasks['summarizer'])} 字符")
        return True
        
    except Exception as e:
        print(f"  ❌ Task 生成失败: {e}")
        return False


def check_task_save():
    """检查 Task 保存"""
    print("\n[Check 4] Task 保存检查")
    try:
        from orchestrator_agent import run_initialization
        
        result = run_initialization(
            company_code="688652.SH",
            company_name="京仪装备"
        )
        
        session_id = result["session_id"]
        tasks_path = result["tasks_path"]
        plan_path = result["plan_path"]
        
        # 检查文件是否存在
        if not os.path.exists(tasks_path):
            print(f"  ❌ Tasks 文件不存在: {tasks_path}")
            return False
        
        if not os.path.exists(plan_path):
            print(f"  ❌ 计划文件不存在: {plan_path}")
            return False
        
        # 检查文件内容
        with open(tasks_path, 'r') as f:
            tasks = json.load(f)
        
        with open(plan_path, 'r') as f:
            plan = json.load(f)
        
        print(f"  ✅ 文件保存成功")
        print(f"     Session: {session_id}")
        print(f"     Tasks: {tasks_path}")
        print(f"     Plan: {plan_path}")
        return True
        
    except Exception as e:
        print(f"  ❌ 保存失败: {e}")
        return False


def check_tool_call_instructions():
    """检查是否包含工具调用说明"""
    print("\n[Check 5] 工具调用说明检查")
    try:
        with open('/Users/allen/.openclaw/workspace/.deepflow/orchestrator_agent.py', 'r') as f:
            content = f.read()
        
        required_markers = [
            "sessions_spawn",
            "sessions_yield",
            "DataManager Worker",
            "Planner Worker",
            "Summarizer Worker"
        ]
        
        for marker in required_markers:
            if marker not in content:
                print(f"  ❌ 缺少说明: {marker}")
                return False
        
        print("  ✅ 工具调用说明完整")
        return True
        
    except Exception as e:
        print(f"  ❌ 检查失败: {e}")
        return False


def main():
    """运行所有检查"""
    print("=" * 60)
    print("Orchestrator V4.0 契约验证")
    print("=" * 60)
    
    checks = [
        ("Python 语法", check_python_syntax),
        ("模块导入", check_imports),
        ("Task 生成", check_task_generation),
        ("Task 保存", check_task_save),
        ("工具调用说明", check_tool_call_instructions),
    ]
    
    results = {}
    for name, check_func in checks:
        try:
            results[name] = check_func()
        except Exception as e:
            print(f"  ❌ 检查异常: {e}")
            results[name] = False
    
    # 汇总
    print("\n" + "=" * 60)
    print("验证结果汇总")
    print("=" * 60)
    
    passed = sum(results.values())
    total = len(results)
    
    for name, result in results.items():
        status = "✅" if result else "❌"
        print(f"{status} {name}")
    
    print(f"\n总计: {passed}/{total} 通过")
    
    if passed == total:
        print("\n🎉 所有检查通过！")
        return 0
    else:
        print("\n⚠️ 部分检查未通过")
        return 1


if __name__ == "__main__":
    sys.exit(main())
