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

    在主 Agent 的 exec 环境中调用，生成执行计划并初始化状态。
    返回包含 spawn_params 的字典，主 Agent 只需将 spawn_params 传给 sessions_spawn 即可启动管线。

    Args:
        topic: 设计主题（必需，>=5字符）
        **kwargs: solution_type, mode, constraints, stakeholders,
                  living_spec（Spec Pro 桥接）

    Returns:
        {
            "session_id": str,
            "base_path": str,
            "plan_path": str,
            "spawn_params": dict,  # 直接传给 sessions_spawn 的参数
        }
    """
    orchestrator = _SolutionDispatcher(topic=topic, spawn_fn=None, **kwargs)
    session_id = orchestrator.init()
    orchestrator.get_all_tasks()
    orchestrator.save_tasks()
    orchestrator.save_execution_plan()

    base_path = orchestrator.base_path
    plan_path = f"{base_path}/execution_plan.json"

    # 自动初始化状态文件
    import json as _json, os as _os
    for old_file in [".completed", ".cron_run_count", ".notified_stages.json"]:
        path = f"{base_path}/{old_file}"
        if _os.path.exists(path):
            _os.remove(path)

    _os.makedirs(base_path, exist_ok=True)
    with open(f"{base_path}/.notified_stages.json", "w") as f:
        _json.dump({"notified": [], "total_messages_sent": 0}, f)
    with open(f"{base_path}/.cron_run_count", "w") as f:
        _json.dump({"count": 0, "max_runs": 20, "run_start_at": "PENDING"}, f)

    # 读取并替换 orchestrator prompt
    import pathlib
    prompt_path = pathlib.Path(__file__).parent / "prompts" / "pipeline_orchestrator_v4.md"
    prompt_template = prompt_path.read_text(encoding="utf-8")
    orchestrator_prompt = prompt_template.replace("{base_path}", base_path).replace("{session_id}", session_id).replace("{plan_path}", plan_path)

    return {
        "session_id": session_id,
        "base_path": base_path,
        "plan_path": plan_path,
        "spawn_params": {
            "runtime": "subagent",
            "mode": "run",
            "label": "solution_orchestrator",
            "task": orchestrator_prompt,
            "runTimeoutSeconds": 3600,
        },
    }


__all__ = ['run_solution_pro']
