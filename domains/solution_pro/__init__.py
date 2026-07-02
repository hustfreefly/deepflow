"""
Solution Pro 模块入口，提供 run_solution_pro 和 run_solution_pro 公共 API

Version: 3.0.0
Author: DeepFlow Solution Pro
Date: 2026-06-28

V3.0: 新增 V2 入口 run_solution_pro()，使用 MasterOrchestrator 三模块架构
V2.2: 迁移到 V6 BlackboardManager API

## 版本选择说明

- **V1 (run_solution_pro)**: 10 阶段单 Orchestrator 架构，向后兼容
  - 适用于：已有 V1 流程、需要固定 10 阶段执行计划
  - 入口：run_solution_pro(topic, **kwargs)

- **run_solution_pro**: 3 模块编排架构（推荐）（Planning → Research → ReviewQC）
  - 适用于：新流程、需要模块化、断点续跑、降级策略
  - 入口：run_solution_pro(user_input, **kwargs)
  - 核心：MasterOrchestrator + PlanningOrchestrator + ResearchOrchestrator + ReviewQCOrchestrator
"""

"""
Solution Pro - 10阶段方案设计管线

## 唯一入口

```python
from domains.solution_pro import run_solution_pro

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
from domains.solution_pro import run_solution_pro

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

import sys as _sys; _p=__import__('pathlib').Path(__file__).resolve(); _r=next((d for d in _p.parents if (d/'core'/'blackboard').is_dir()),None); _sys.path.insert(0,str(_r)) if _r and str(_r) not in _sys.path else None  # 契约笼子: 自动发现 .deepflow 根目录
import json
import os
import pathlib
from datetime import datetime, timezone
from core.blackboard.context_injector import build_agent_context
from pathlib import Path

from .orchestrator_agent import _SolutionDispatcher
from .blackboard import BlackboardManager
from .master_orchestrator import MasterOrchestrator


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
    # Record pipeline start time for watcher timeout detection
    run_start_at = datetime.now(timezone.utc).isoformat()

    orchestrator = _SolutionDispatcher(topic=topic, spawn_fn=None, **kwargs)
    session_id = orchestrator.init()
    orchestrator.get_all_tasks()
    orchestrator.save_tasks()
    orchestrator.save_execution_plan()

    # 使用 V6 BlackboardManager 统一管理 session 目录
    base_path = orchestrator.base_path
    bm = BlackboardManager(session_id, base_dir=Path(base_path).parent)
    bm.init_session()

    # 清理旧文件（含 watcher 状态，防止重跑时 circuit break 误报）
    for old_file in [".completed", ".cron_run_count", ".notified_stages.json",
                     ".watcher_no_output_count", ".watcher_should_remove", ".pipeline_watcher.lock"]:
        old_path = bm.session_dir / old_file
        if old_path.exists():
            old_path.unlink()

    # 初始化元数据文件
    bm.write(".notified_stages.json", {"notified": [], "total_messages_sent": 0})
    bm.write(".cron_run_count", {"count": 0, "max_runs": 20, "run_start_at": "PENDING"})

    # 读取并替换 orchestrator prompt
    prompt_path = pathlib.Path(__file__).parent / "prompts" / "pipeline_orchestrator.md"
    prompt_template = prompt_path.read_text(encoding="utf-8")
    session_dir = str(bm.session_dir)
    plan_path = f"{session_dir}/execution_plan.json"
    # ── FIX-1/2/4/5: 注入上下文到 orchestrator prompt ──
    deepflow_root = str(Path(__file__).resolve().parent.parent.parent)
    agent_context = build_agent_context(
        deepflow_root=Path(deepflow_root),
        blackboard_id=session_id,
        include_schema=False,
        include_analysis_workflow=True,
    )

    orchestrator_prompt = (
        agent_context
        + "\n\n---\n\n"
        + prompt_template
        .replace("{base_path}", session_dir)
        .replace("{session_id}", session_id)
        .replace("{plan_path}", plan_path)
    )

    # Watcher integration: provide all info needed for main Agent to create cron
    watcher_config_rel = "domains/solution_pro/config/watcher_config.json"
    watcher_config_abs = os.path.join(deepflow_root, watcher_config_rel)

    return {
        "session_id": session_id,
        "base_path": session_dir,
        "plan_path": plan_path,
        "spawn_params": {
            "runtime": "subagent",
            "mode": "run",
            "label": "solution_orchestrator",
            "task": orchestrator_prompt,
        },
        # --- Watcher fields (new, backward-compatible) ---
        "run_start_at": run_start_at,
        "watcher_config": watcher_config_rel,
        "watcher_config_abs": watcher_config_abs,
        "deepflow_root": deepflow_root,
    }


def run_solution_pro(user_input: str, **kwargs):
    """
    Solution Pro V2 入口（Agent-centric 架构）

    初始化 Blackboard + frozen_spec，生成 V2 Orchestrator prompt，
    返回 spawn_params 供主 Agent 调用 sessions_spawn 启动管线。

    架构：
      Main Agent (depth-0)
        → sessions_spawn → V2 Orchestrator (depth-1)
          → sessions_spawn → Module Agents (depth-2)
            → sessions_spawn → Workers (depth-3)

    Args:
        user_input: 用户输入（需求描述）
        **kwargs: topic, solution_type, mode, domain, constraints, stakeholders,
                  living_spec（Spec Pro 桥接）

    Returns:
        {
            "session_id": str,
            "base_path": str,
            "spawn_params": dict,  # 直接传给 sessions_spawn
        }
    """
    # 1. 初始化 Blackboard session
    topic = kwargs.get("topic", user_input[:50])
    bm = BlackboardManager(topic, base_dir=Path(__file__).parent / "blackboard_sessions")
    bm.init_session()
    session_id = bm.session_id
    session_dir = str(bm.session_dir)

    # 2. 使用 frozen_spec.py 生成完整 Frozen Spec（含 REQ-IDs、executive_summary、requirement_groups）
    from domains.solution_pro.frozen_spec import build_frozen_spec
    living_spec = kwargs.get("living_spec")
    frozen_spec = build_frozen_spec(
        topic=topic,
        constraints=kwargs.get("constraints", []),
        living_spec=living_spec,
    )
    bm.write("data/frozen_spec.json", frozen_spec)

    # 3. 初始化 master_state
    bm.write("master_state.json", {
        "session_id": session_id,
        "status": "initialized",
        "current_module": None,
        "completed_modules": [],
        "failed_modules": [],
        "degraded_modules": [],
    })

    # 4. 清理旧文件（断点续跑时防止误判）
    for old_file in [".completed"]:
        old_path = bm.session_dir / old_file
        if old_path.exists():
            old_path.unlink()

    # 5. 读取 V2 Orchestrator prompt 模板并填充变量
    prompt_path = pathlib.Path(__file__).parent / "prompts" / "orchestrator.md"
    prompt_template = prompt_path.read_text(encoding="utf-8")

    deepflow_root = str(Path(__file__).resolve().parent.parent.parent)

    # 注入 Agent 上下文（Blackboard API 指南 + 路径信息）
    agent_context = build_agent_context(
        deepflow_root=Path(deepflow_root),
        blackboard_id=session_id,
        include_schema=False,
        include_analysis_workflow=True,
    )

    import json as _json
    config_json = _json.dumps(kwargs, ensure_ascii=False, indent=2)

    orchestrator_prompt = (
        agent_context
        + "\n\n---\n\n"
        + prompt_template
        .replace("{session_id}", session_id)
        .replace("{user_input}", user_input)
        .replace("{config}", config_json)
    )

    # 6. 返回 spawn_params（主 Agent 用 sessions_spawn 启动）
    return {
        "session_id": session_id,
        "base_path": session_dir,
        "spawn_params": {
            "runtime": "subagent",
            "mode": "run",
            "label": "solution_orchestrator",
            "task": orchestrator_prompt,
            "cwd": deepflow_root,
            "lightContext": True,
        },
    }


__all__ = ['run_solution_pro']