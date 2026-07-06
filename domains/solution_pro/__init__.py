"""
Solution Pro 模块入口

Version: 2.0.0
Date: 2026-07-05

2.0.0: AI Native 重构，三模块架构（Planning → Research → Summary）
2.0.0: 2.0.0 入口 run_solution_pro()，使用 MasterOrchestrator 三模块架构

## 唯一入口

```python
from domains.solution_pro import run_solution_pro
result = run_solution_pro(user_input="...", topic="...", ...)
sessions_spawn(**result["spawn_params"])
```

- **run_solution_pro**: 3 模块编排架构（推荐）（Planning → Research → Summary）
  - 适用于：新流程、需要模块化、断点续跑、降级策略
  - 入口：run_solution_pro(user_input, **kwargs)
  - 核心：MasterOrchestrator + PlanningOrchestrator + ResearchOrchestrator + SummaryOrchestrator
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
# "session_id": "sol_xxx",
# "base_path": "/path/to/blackboard/sol_xxx",
# "plan_path": "/path/to/blackboard/sol_xxx/execution_plan.json",
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
from typing import Optional  # 契约笼子：_try_load_handoff_package 返回类型
from core.blackboard.context_injector import build_agent_context
from pathlib import Path

from .blackboard import BlackboardManager
from .master_orchestrator import MasterOrchestrator


def _try_load_handoff_package(bm: BlackboardManager) -> Optional[dict]:
    """从 blackboard 加载 Spec Pro 的 handoff package（契约笼子验证版）。

    设计意图：
      当 living_spec 未通过 kwargs 传入时，从 blackboard 扫描
      最新的 spec_handoff_package.json，用 Pydantic 模型验证后
      提取 living_spec。验证失败 → raise ValueError，不静默降级。

    Args:
        bm: 已初始化的 BlackboardManager 实例

    Returns:
        验证后的 living_spec dict，如果找不到 handoff package 则返回 None

    Raises:
        ValueError: handoff_allowed=False 或契约验证失败时抛出
    """
    import glob

    # 契约笼子：导入 Pydantic 模型
    from contracts.shared.handoff_contract import HandoffPackage

    # 在 blackboard 根目录下扫描最新的 spec/spec_handoff_package.json
    # 设计意图：spec_pro 和 solution_pro 共享同一个 blackboard 根目录，
    #          但各自有独立的 session 子目录，所以需要扫描查找。
    blackboard_root = bm._base  # blackboard 根目录
    pattern = str(blackboard_root / "*" / "spec" / "spec_handoff_package.json")
    candidates = sorted(glob.glob(pattern), key=lambda p: Path(p).stat().st_mtime, reverse=True)

    if not candidates:
        # 没有 handoff package → 返回 None，让调用方决定后续行为
        return None

    # 读取最新的 handoff package
    latest_path = Path(candidates[0])
    with open(latest_path, "r", encoding="utf-8") as f:
        raw_package = json.load(f)

    # 契约笼子：Pydantic 验证（失败直接 raise ValueError）
    try:
        package = HandoffPackage(**raw_package)
    except Exception as e:
        raise ValueError(
            f"handoff package 契约验证失败 ({latest_path}): {e}"
        ) from e

    # 契约铁律：handoff_allowed=False → 阻断，不静默继续
    if not package.handoff_allowed:
        raise ValueError(
            f"Spec Pro handoff 被拒绝: block_reason={package.block_reason}"
        )

    # 验证通过 → 提取 living_spec
    return package.living_spec


def run_solution_pro(user_input: str, **kwargs):
    """
    Solution Pro 2.0.0 入口（Agent-centric 架构）

    初始化 Blackboard + frozen_spec，生成 Orchestrator prompt，
    返回 spawn_params 供主 Agent 调用 sessions_spawn 启动管线。

    架构：
      Main Agent (depth-0)
        → sessions_spawn → Orchestrator (depth-1)
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
    # 契约笼子（2026-07-05）：统一 blackboard 路径，走默认 .deepflow/blackboard/
    # 确保 Ship Pro 能从统一路径读取 Solution Pro 输出
    bm = BlackboardManager(topic)  # 删掉 base_dir= → 走 PathConfig 默认路径
    bm.init_session()
    session_id = bm.session_id
    session_dir = str(bm.session_dir)

    # 2. 使用 frozen_spec.py 生成完整 Frozen Spec（含 REQ-IDs、executive_summary、requirement_groups）
    from domains.solution_pro.frozen_spec import build_frozen_spec
    living_spec = kwargs.get("living_spec")

    # 契约笼子（2026-07-06）：handoff package 消费逻辑
    # 设计意图：当 living_spec 未通过 kwargs 直接传入时，
    #          从 blackboard 读取 spec_pro 产出的 handoff package，
    #          用 Pydantic 模型验证后提取 living_spec。
    #          确保 handoff_allowed=False 时立即阻断，不静默继续。
    if living_spec is None:
        living_spec = _try_load_handoff_package(bm)

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

    # 5. 读取 Orchestrator prompt 模板并填充变量
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
        .replace("{deepflow_root}", deepflow_root)
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


# 契约笼子（2026-07-05）：显式导出 2.0.0 和 2.0.0，避免函数覆盖
__all__ = ['run_solution_pro']