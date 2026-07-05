#!/usr/bin/env python3
"""
Solution Pro 任务执行脚本
"""
import json
import os
from pathlib import Path

# 添加 deepflow 到路径
DEEPFLOW_BASE = os.environ.get("DEEPFLOW_BASE", str(Path(__file__).resolve().parent.parent))

from domains.solution_pro.orchestrator_agent import SolutionOrchestratorV21
import core.bootstrap

# 从命令行读取参数
if len(sys.argv) < 2:
    print("Usage: python run_solution_task.py '<json_context>'")
    sys.exit(1)

context_json = sys.argv[1]
context = json.loads(context_json)

# 创建 Orchestrator
orch = SolutionOrchestratorV21(
    topic=context.get("topic"),
    solution_type=context.get("solution_type", "architecture"),
    mode=context.get("mode", "standard"),
    constraints=context.get("constraints", []),
    stakeholders=context.get("stakeholders", []),
    session_prefix=context.get("session_prefix")
)

# 初始化
session_id = orch.init()
print(f"Session initialized: {session_id}")

# 获取所有任务
tasks = orch.get_all_tasks()
print(f"Generated {len(tasks)} task stages")

# 保存执行计划
orch.save_execution_plan()
print("Execution plan saved")

# 保存任务详情
orch.save_tasks()
print("Tasks saved")

# 输出结果
result = {
    "status": "initialized",
    "session_id": session_id,
    "base_path": orch.base_path,
    "tasks_count": len(tasks),
    "task_stages": list(tasks.keys())
}

print(json.dumps(result, indent=2, ensure_ascii=False))
