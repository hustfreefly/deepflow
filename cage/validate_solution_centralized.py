#!/usr/bin/env python3
"""
Solution 中心化写入方案验证脚本
"""

import sys
import os

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
print("Solution 中心化写入方案验证")
print("="*70)

# 阶段1验证：planner task 是否使用新模式
tb_file = f"{DEEPFLOW_BASE}/domains/solution/task_builder.py"
if os.path.exists(tb_file):
    with open(tb_file, 'r') as f:
        content = f.read()
    
    # 检查是否有返回JSON的指令
    has_return_json = '"status": "completed"' in content or "返回JSON" in content
    check("Task 包含返回JSON指令", has_return_json, "未找到返回JSON的指令")
    
    # 检查是否还有直接写入指令（应该减少）
    has_write_instruction = '文件路径' in content and 'write' in content
    check("Task 不再直接写入", not has_write_instruction, "仍包含直接写入指令")

# 阶段2验证：orchestrator 是否处理返回值
orch_file = f"{DEEPFLOW_BASE}/domains/solution/orchestrator.py"
if os.path.exists(orch_file):
    with open(orch_file, 'r') as f:
        content = f.read()
    
    # 检查是否有处理返回值的逻辑
    has_result_handling = "result" in content and "_save_to_blackboard" in content
    check("Orchestrator 处理返回值", has_result_handling, "未找到返回值处理逻辑")

# 阶段3验证：端到端测试（简化版）
blackboard_dir = f"{DEEPFLOW_BASE}/blackboard"
if os.path.exists(blackboard_dir):
    sessions = os.listdir(blackboard_dir)
    planning_files = []
    for session in sessions:
        planning_path = f"{blackboard_dir}/{session}/stages/planning.json"
        if os.path.exists(planning_path):
            planning_files.append(planning_path)
    
    check("Blackboard 包含 planning.json", len(planning_files) > 0, 
          f"未找到 planning.json 文件")

print("\n" + "="*70)
print(f"验证结果: {passed}/{passed+failed} 通过")
print("="*70)

sys.exit(0 if failed == 0 else 1)
