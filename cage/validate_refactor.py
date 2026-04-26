#!/usr/bin/env python3
"""
Solution 模块重构契约验证脚本
版本: 2026-04-26-v1

验证项：
1. 新建文件存在性检查
2. 禁止 from openclaw import 检查
3. SolutionOrchestratorV2 类初始化测试
4. Task 生成测试
5. 执行计划保存测试
6. Investment 模块未受影响检查
"""

import sys
import os
import json
import subprocess

DEEPFLOW_BASE = "/Users/allen/.openclaw/workspace/.deepflow"
sys.path.insert(0, DEEPFLOW_BASE)

# =============================================================================
# 验证结果收集
# =============================================================================
passed = 0
failed = 0
errors = []

def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        errors.append(f"❌ {name}: {detail}")
        print(f"  ❌ {name} - {detail}")

# =============================================================================
# 1. 文件存在性检查
# =============================================================================
print("\n[1/6] 文件存在性检查")

check(
    "orchestrator_agent.py 存在",
    os.path.exists(f"{DEEPFLOW_BASE}/domains/solution/orchestrator_agent.py"),
    "文件不存在"
)

check(
    "task_builder.py 存在",
    os.path.exists(f"{DEEPFLOW_BASE}/domains/solution/task_builder.py"),
    "文件不存在"
)

check(
    "orchestrator.py 存在（向后兼容）",
    os.path.exists(f"{DEEPFLOW_BASE}/domains/solution/orchestrator.py"),
    "文件不存在"
)

# =============================================================================
# 2. 禁止 from openclaw import 检查
# =============================================================================
print("\n[2/6] 禁止 from openclaw import 检查")

def check_no_openclaw_import(filepath: str, is_new_file: bool = True):
    """检查文件是否包含 from openclaw import
    
    Args:
        filepath: 文件路径
        is_new_file: 是否新建文件（新建文件必须无 openclaw import，旧文件豁免）
    """
    if not os.path.exists(filepath):
        check(f"{os.path.basename(filepath)} 无 openclaw import", False, "文件不存在")
        return
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    has_import = 'from openclaw import' in content
    
    if is_new_file:
        check(
            f"{os.path.basename(filepath)} 无 openclaw import",
            not has_import,
            f"发现 'from openclaw import'" if has_import else ""
        )
    else:
        # 旧文件：记录但不作为失败
        if has_import:
            print(f"  ℹ️  {os.path.basename(filepath)} 包含 'from openclaw import'（旧文件，向后兼容）")
        else:
            print(f"  ✅ {os.path.basename(filepath)} 无 openclaw import")

check_no_openclaw_import(f"{DEEPFLOW_BASE}/domains/solution/orchestrator_agent.py", is_new_file=True)
check_no_openclaw_import(f"{DEEPFLOW_BASE}/domains/solution/task_builder.py", is_new_file=True)
check_no_openclaw_import(f"{DEEPFLOW_BASE}/domains/solution/orchestrator.py", is_new_file=False)

# =============================================================================
# 3. SolutionOrchestratorV2 类初始化测试
# =============================================================================
print("\n[3/6] SolutionOrchestratorV2 初始化测试")

try:
    from domains.solution.orchestrator_agent import SolutionOrchestratorV2
    check("SolutionOrchestratorV2 可导入", True)
    
    orch = SolutionOrchestratorV2(
        topic="测试系统",
        solution_type="architecture",
        mode="standard",
        constraints=["高并发"],
        stakeholders=["技术团队"]
    )
    check("SolutionOrchestratorV2 可实例化", True)
    
    session_id = orch.init()
    check(
        "init() 返回 session_id",
        session_id is not None and len(session_id) > 0,
        f"session_id={session_id}"
    )
    
    check(
        "Blackboard 目录已创建",
        os.path.exists(f"{DEEPFLOW_BASE}/blackboard/{session_id}"),
        "目录不存在"
    )
    
    check(
        "data 子目录已创建",
        os.path.exists(f"{DEEPFLOW_BASE}/blackboard/{session_id}/data"),
        "目录不存在"
    )
    
    check(
        "stages 子目录已创建",
        os.path.exists(f"{DEEPFLOW_BASE}/blackboard/{session_id}/stages"),
        "目录不存在"
    )
    
except Exception as e:
    check("SolutionOrchestratorV2 初始化", False, str(e))

# =============================================================================
# 4. Task 生成测试
# =============================================================================
print("\n[4/6] Task 生成测试")

try:
    tasks = orch.get_all_tasks()
    check(
        "get_all_tasks() 返回 dict",
        isinstance(tasks, dict),
        f"类型={type(tasks)}"
    )
    
    expected_stages = ["data_collection", "planning", "research", "design", "audit", "fix", "deliver"]
    check(
        "standard 模式包含 7 个阶段",
        len(tasks) == 7 and all(s in tasks for s in expected_stages),
        f"实际阶段={list(tasks.keys())}"
    )
    
    # 测试 quick 模式
    orch_quick = SolutionOrchestratorV2(
        topic="快速方案",
        solution_type="business",
        mode="quick"
    )
    orch_quick.init()
    tasks_quick = orch_quick.get_all_tasks()
    expected_quick = ["planning", "design", "deliver"]
    check(
        "quick 模式包含 3 个阶段",
        len(tasks_quick) == 3 and all(s in tasks_quick for s in expected_quick),
        f"实际阶段={list(tasks_quick.keys())}"
    )
    
    # 检查 research 阶段是并行（dict）
    check(
        "research 阶段是并行任务（dict）",
        isinstance(tasks.get("research"), dict),
        f"类型={type(tasks.get('research'))}"
    )
    
    # 检查串行阶段是字符串
    check(
        "planning 阶段是串行任务（str）",
        isinstance(tasks.get("planning"), str),
        f"类型={type(tasks.get('planning'))}"
    )
    
except Exception as e:
    check("Task 生成", False, str(e))

# =============================================================================
# 5. 执行计划保存测试
# =============================================================================
print("\n[5/6] 执行计划保存测试")

try:
    plan = orch.save_execution_plan()
    check(
        "save_execution_plan() 返回 dict",
        isinstance(plan, dict),
        f"类型={type(plan)}"
    )
    
    check(
        "plan 包含 session_id",
        "session_id" in plan and plan["session_id"] == session_id,
        "session_id 不匹配"
    )
    
    check(
        "plan 包含 phases",
        "phases" in plan and isinstance(plan["phases"], list),
        "phases 不存在"
    )
    
    check(
        "phases 数量正确（7个）",
        len(plan["phases"]) == 7,
        f"实际={len(plan['phases'])}"
    )
    
    # 检查 execution_plan.json 文件
    plan_path = f"{DEEPFLOW_BASE}/blackboard/{session_id}/execution_plan.json"
    check(
        "execution_plan.json 文件已创建",
        os.path.exists(plan_path),
        "文件不存在"
    )
    
    # 验证 JSON 可解析
    with open(plan_path, 'r', encoding='utf-8') as f:
        loaded_plan = json.load(f)
    check(
        "execution_plan.json 是有效 JSON",
        loaded_plan["session_id"] == session_id,
        "JSON 解析失败或 session_id 不匹配"
    )
    
    # 检查 tasks.json
    tasks_path = f"{DEEPFLOW_BASE}/blackboard/{session_id}/tasks.json"
    orch.save_tasks()
    check(
        "tasks.json 文件已创建",
        os.path.exists(tasks_path),
        "文件不存在"
    )
    
except Exception as e:
    check("执行计划保存", False, str(e))

# =============================================================================
# 6. Investment 模块未受影响检查
# =============================================================================
print("\n[6/6] Investment 模块未受影响检查")

try:
    # 检查 Investment 文件未修改
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD", "--", "domains/investment/"],
        cwd=DEEPFLOW_BASE,
        capture_output=True,
        text=True
    )
    check(
        "Investment 目录无修改",
        result.stdout.strip() == "",
        f"修改文件: {result.stdout.strip()}"
    )
    
    # 检查 core/orchestrator_base.py 未修改（Solution 不应修改基类）
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD", "--", "core/orchestrator_base.py"],
        cwd=DEEPFLOW_BASE,
        capture_output=True,
        text=True
    )
    check(
        "core/orchestrator_base.py 无修改",
        result.stdout.strip() == "",
        f"修改文件: {result.stdout.strip()}"
    )
    
except Exception as e:
    check("Investment 检查", False, str(e))

# =============================================================================
# 总结
# =============================================================================
print("\n" + "=" * 70)
print(f"验证结果: {passed}/{passed+failed} 通过")
print("=" * 70)

if errors:
    print("\n错误详情:")
    for err in errors:
        print(f"  {err}")
    sys.exit(1)
else:
    print("\n✅ 全部验证通过！")
    sys.exit(0)
