#!/usr/bin/env python3
"""
DeepFlow V2.0 - Solution Designer Domain Package
"""


# 🚨 最高级教训：exec 环境禁止 import openclaw（2026-04-26）
# 本模块 V2.0 已重构为纯调度架构，不再直接调用 openclaw
# 如需 spawn Workers，请使用 domains/solution/orchestrator_agent.py
# 或参考 Investment V4.0 架构 (core/orchestrator_agent.py)

from .orchestrator import SolutionOrchestrator, run_solution_design
from .orchestrator_agent import SolutionOrchestratorV2
from .task_builder import (
    build_data_collection_task,
    build_planner_task,
    build_researcher_task,
    build_designer_task,
    build_auditor_task,
    build_fixer_task,
    build_deliver_task
)

__all__ = [
    "SolutionOrchestrator",
    "SolutionOrchestratorV2",
    "run_solution_design",
    "build_data_collection_task",
    "build_planner_task",
    "build_researcher_task",
    "build_designer_task",
    "build_auditor_task",
    "build_fixer_task",
    "build_deliver_task"
]
