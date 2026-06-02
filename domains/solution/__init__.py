"""
Solution Pro 模块入口，提供 run_solution_pro 公共 API

Version: 2.1.0
Author: DeepFlow Solution Pro
Date: 2026-06-01
"""

"""
Solution Pro - 10阶段方案设计管线

## 唯一入口

```python
from domains.solution import run_solution_pro

result = run_solution_pro(
    topic="设计一个AI算力调度平台",
    solution_type="architecture",  # 可选
    mode="standard",  # 可选
    constraints=["10000+并发"],  # 可选
    stakeholders=["技术团队"],  # 可选
)

# result = {
#     "session_id": "sol_xxx",
#     "base_path": "/path/to/blackboard/sol_xxx",
#     "plan_path": "/path/to/blackboard/sol_xxx/execution_plan.json",
# }
```

## 主 Agent 执行流程

在主 Agent 的 exec 中生成任务与执行计划：
```python
from domains.solution import run_solution_pro

result = run_solution_pro(
    topic="...",
    solution_type="architecture",
    mode="standard",
    constraints=[],
    stakeholders=[],
)
print(result["plan_path"])
```

## 架构

```
主 Agent exec
  └── run_solution_pro(topic)
        └── _SolutionDispatcher.init() → 生成 session_id + blackboard
        └── _SolutionDispatcher.save_tasks()
        └── _SolutionDispatcher.save_execution_plan()
              └── 生成固定10阶段 execution_plan.json + tasks.json
                    ├── LLM Orchestrator 按 execution_plan 调度 workers
                    ├── Planner 完成后刷新 control_contract.json
                    └── expected_output_path 作为完成判定契约
```
"""

from .orchestrator_agent import _SolutionDispatcher


def run_solution_pro(topic: str, **kwargs):
    """
    Solution Pro 唯一入口

    在主 Agent 的 exec 环境中调用，生成执行计划。
    返回路径供主 Agent 通过 sessions_spawn 工具启动子 Agent。

    Args:
        topic: 设计主题（必需，>=5字符）
        **kwargs: solution_type, mode, constraints, stakeholders,
                  living_spec（Spec Pro 桥接）

    Returns:
        {
            "session_id": str,
            "base_path": str,
            "plan_path": str,
        }
    """
    orchestrator = _SolutionDispatcher(topic=topic, spawn_fn=None, **kwargs)
    session_id = orchestrator.init()
    orchestrator.get_all_tasks()
    orchestrator.save_tasks()
    orchestrator.save_execution_plan()

    plan_path = f"{orchestrator.base_path}/execution_plan.json"

    return {
        "session_id": session_id,
        "base_path": orchestrator.base_path,
        "plan_path": plan_path,
    }


__all__ = ['run_solution_pro']
